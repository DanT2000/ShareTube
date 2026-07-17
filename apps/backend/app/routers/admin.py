"""Admin API. All endpoints require an admin session; secrets are always masked."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import ADMIN_COOKIE, require_admin
from ..logging_config import get_logger
from ..models import (
    AuditLog,
    CookieProfile,
    DownloadJob,
    JobStatus,
    ProxyProfile,
    StoredFile,
    SystemSetting,
    User,
)
from ..outbound import manager as route_mgr
from ..outbound.xray import validate_xray_config
from ..queue import request_cancel
from ..schemas import HttpProxyCreate, ProxyProfileOut, XrayProfileCreate
from ..security.crypto import encrypt
from ..security.signed_urls import make_admin_session
from ..security.telegram_auth import InitDataError, validate_login_widget

log = get_logger("admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _audit(session: AsyncSession, admin: User, action: str, target: str | None = None,
                 detail: dict | None = None) -> None:
    session.add(AuditLog(actor=f"admin:{admin.id}", action=action, target=target, detail=detail))


# ---------------- auth ----------------
@router.post("/login")
async def admin_login(payload: dict, response: Response,
                      session: AsyncSession = Depends(get_session)):
    """Admin login via Telegram Login Widget; only configured admin ids are accepted."""
    try:
        data = validate_login_widget(dict(payload))
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail="invalid telegram auth") from exc
    tid = int(data["id"])
    if tid not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="not an admin")
    from ..deps import _get_or_create_user_by_telegram
    user = await _get_or_create_user_by_telegram(session, data)
    user.is_admin = True
    await session.commit()
    secure = settings.PUBLIC_BASE_URL.startswith("https")
    response.set_cookie(ADMIN_COOKIE, make_admin_session(str(user.id)), httponly=True,
                        secure=secure, samesite="lax", max_age=settings.ADMIN_SESSION_TTL_HOURS * 3600)
    return {"ok": True}


@router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE)
    return {"ok": True}


# ---------------- dashboard ----------------
@router.get("/dashboard")
async def dashboard(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    async def count(*where):
        return (await session.execute(select(func.count()).select_from(DownloadJob).where(*where))).scalar_one()

    active = await count(DownloadJob.status.in_([s.value for s in (
        JobStatus.DOWNLOADING, JobStatus.MERGING, JobStatus.CONVERTING, JobStatus.UPLOADING)]))
    queued = await count(DownloadJob.status == JobStatus.QUEUED.value)
    failed = await count(DownloadJob.status == JobStatus.FAILED.value)
    done = await count(DownloadJob.status == JobStatus.DONE.value)
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    total_bytes = (await session.execute(
        select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(StoredFile.deleted_at.is_(None))
    )).scalar_one()
    disk = shutil.disk_usage(settings.STORAGE_DIR) if _exists(settings.STORAGE_DIR) else None
    return {
        "jobs": {"active": active, "queued": queued, "failed": failed, "done": done},
        "users": users,
        "storage": {
            "used_bytes": int(total_bytes),
            "cap_bytes": settings.max_storage_bytes,
            "disk_total": disk.total if disk else None,
            "disk_free": disk.free if disk else None,
        },
    }


def _exists(p: str) -> bool:
    import os
    return os.path.isdir(p)


@router.get("/jobs")
async def admin_jobs(status: str | None = None, limit: int = 50,
                     admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    q = select(DownloadJob).order_by(DownloadJob.created_at.desc()).limit(min(limit, 200))
    if status:
        q = q.where(DownloadJob.status == status)
    rows = (await session.execute(q)).scalars().all()
    return [{"id": r.id, "user_id": r.user_id, "source": r.source, "status": r.status,
             "content_type": r.content_type, "progress": r.progress, "stage": r.stage,
             "actual_size_bytes": r.actual_size_bytes, "error_code": r.error_code,
             "created_at": r.created_at, "url": r.normalized_url[:120]} for r in rows]


@router.post("/jobs/{job_id}/cancel")
async def admin_cancel(job_id: str, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    job = await session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="not found")
    await request_cancel(job_id)
    job.status = JobStatus.CANCELLED.value
    job.error_code = "cancelled"
    await _audit(session, admin, "cancel_job", job_id)
    await session.commit()
    return {"ok": True}


@router.delete("/jobs/{job_id}/file")
async def admin_delete_file(job_id: str, admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    job = await session.get(DownloadJob, job_id)
    if not job or not job.stored_file_id:
        raise HTTPException(status_code=404, detail="no file")
    sf = await session.get(StoredFile, job.stored_file_id)
    if sf and not sf.deleted_at:
        from ..storage import get_storage_provider
        await get_storage_provider().delete(sf.rel_path)
        sf.deleted_at = datetime.now(timezone.utc)
    await _audit(session, admin, "delete_file", job_id)
    await session.commit()
    return {"ok": True}


# ---------------- users ----------------
@router.get("/users")
async def admin_users(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(User).order_by(User.created_at.desc()).limit(200))).scalars().all()
    return [{"id": u.id, "display_name": u.display_name, "is_admin": u.is_admin,
             "is_blocked": u.is_blocked, "quota_daily_jobs": u.quota_daily_jobs,
             "created_at": u.created_at} for u in rows]


@router.post("/users/{user_id}/block")
async def admin_block(user_id: int, blocked: bool = True, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    u.is_blocked = blocked
    await _audit(session, admin, "block_user" if blocked else "unblock_user", str(user_id))
    await session.commit()
    return {"ok": True}


@router.post("/users/{user_id}/quota")
async def admin_quota(user_id: int, daily_jobs: int | None = None, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="not found")
    u.quota_daily_jobs = daily_jobs
    await _audit(session, admin, "set_quota", str(user_id), {"daily_jobs": daily_jobs})
    await session.commit()
    return {"ok": True}


# ---------------- proxy / xray profiles ----------------
@router.get("/proxies", response_model=list[ProxyProfileOut])
async def list_proxies(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    return await route_mgr.list_profiles(session)


@router.post("/proxies/http", response_model=ProxyProfileOut)
async def create_http_proxy(body: HttpProxyCreate, admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    row = await route_mgr.create_http_profile(
        session, body.name, body.url, is_primary=body.is_primary, is_backup=body.is_backup,
        priority=body.priority, bound_sources=body.bound_sources)
    await _audit(session, admin, "create_http_proxy", row.name)
    await session.commit()
    return row


@router.post("/proxies/xray", response_model=ProxyProfileOut)
async def create_xray_proxy(body: XrayProfileCreate, admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    # Validate JSON configs before storing; URIs/subscriptions pass through.
    if body.config_or_uri.strip().startswith("{"):
        ok, msg = validate_xray_config(body.config_or_uri)
        if not ok:
            raise HTTPException(status_code=400, detail={"code": "invalid_xray", "message": msg})
    row = await route_mgr.create_xray_profile(
        session, body.name, body.config_or_uri, is_primary=body.is_primary,
        is_backup=body.is_backup, priority=body.priority)
    await _audit(session, admin, "create_xray_proxy", row.name)
    await session.commit()
    return row


@router.post("/proxies/{pid}/check")
async def check_proxy(pid: int, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    row = await session.get(ProxyProfile, pid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    await route_mgr.run_check(session, row)
    await session.commit()
    return {"status": row.last_status, "latency_ms": row.last_latency_ms,
            "error_category": row.last_error_category, "checked_at": row.last_checked_at}


@router.post("/proxies/{pid}/toggle")
async def toggle_proxy(pid: int, enabled: bool, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    row = await session.get(ProxyProfile, pid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    row.enabled = enabled
    await _audit(session, admin, "toggle_proxy", row.name, {"enabled": enabled})
    await session.commit()
    return {"ok": True}


@router.post("/proxies/{pid}/role")
async def set_role(pid: int, primary: bool = False, backup: bool = False,
                   admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    row = await session.get(ProxyProfile, pid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    if primary:
        for other in await route_mgr.list_profiles(session):
            other.is_primary = False
        row.is_primary = True
    if backup:
        row.is_backup = True
    await _audit(session, admin, "set_proxy_role", row.name, {"primary": primary, "backup": backup})
    await session.commit()
    return {"ok": True}


@router.delete("/proxies/{pid}")
async def delete_proxy(pid: int, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    row = await session.get(ProxyProfile, pid)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(row)
    await _audit(session, admin, "delete_proxy", str(pid))
    await session.commit()
    return {"ok": True}


# ---------------- cookies ----------------
@router.get("/cookies")
async def list_cookies(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(CookieProfile))).scalars().all()
    # never return cookie data
    return [{"id": c.id, "source": c.source, "name": c.name, "enabled": c.enabled,
             "health_status": c.health_status, "last_checked_at": c.last_checked_at,
             "has_data": c.encrypted_data is not None} for c in rows]


@router.post("/cookies")
async def upsert_cookie(source: str, name: str, cookie_data: str,
                        admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        select(CookieProfile).where(CookieProfile.source == source, CookieProfile.name == name)
    )).scalar_one_or_none()
    if not row:
        row = CookieProfile(source=source, name=name)
        session.add(row)
    row.encrypted_data = encrypt(cookie_data)
    row.health_status = "unknown"
    await _audit(session, admin, "upsert_cookie", f"{source}:{name}")  # never log the data
    await session.commit()
    return {"ok": True, "id": row.id}


# ---------------- system ----------------
@router.get("/versions")
async def versions(admin: User = Depends(require_admin)):
    return get_tool_versions()


@router.get("/settings")
async def get_settings_view(admin: User = Depends(require_admin)):
    """Return non-secret runtime settings for display."""
    return {
        "limits": {
            "CLOUD_BOT_SAFE_LIMIT_MB": settings.CLOUD_BOT_SAFE_LIMIT_MB,
            "LOCAL_BOT_SAFE_LIMIT_MB": settings.LOCAL_BOT_SAFE_LIMIT_MB,
            "MAX_DOWNLOAD_SIZE_MB": settings.MAX_DOWNLOAD_SIZE_MB,
            "DOWNLOAD_LINK_TTL_HOURS": settings.DOWNLOAD_LINK_TTL_HOURS,
            "MAX_STORAGE_GB": settings.MAX_STORAGE_GB,
            "MAX_ACTIVE_JOBS_PER_USER": settings.MAX_ACTIVE_JOBS_PER_USER,
            "MAX_GLOBAL_DOWNLOADS": settings.MAX_GLOBAL_DOWNLOADS,
            "MAX_GLOBAL_TRANSCODES": settings.MAX_GLOBAL_TRANSCODES,
            "MAX_PLAYLIST_ITEMS": settings.MAX_PLAYLIST_ITEMS,
        },
        "telegram": {
            "bot_username": settings.BOT_USERNAME,
            "mode": "webhook" if settings.TELEGRAM_USE_WEBHOOK else "polling",
            "local_bot_api": settings.LOCAL_BOT_API_ENABLED,
            "token_fingerprint": _fp(settings.BOT_TOKEN),
        },
        "network": {"outbound_required": settings.OUTBOUND_REQUIRED},
        "storage_provider": settings.STORAGE_PROVIDER,
    }


@router.get("/logs")
async def audit_logs(limit: int = 100, admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    )).scalars().all()
    return [{"created_at": r.created_at, "actor": r.actor, "action": r.action,
             "target": r.target, "detail": r.detail} for r in rows]


@router.post("/cleanup")
async def run_cleanup(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    from ..services.storage_service import cleanup_expired, cleanup_stale_tmp, enforce_storage_cap
    expired = await cleanup_expired(session)
    freed = await enforce_storage_cap(session)
    stale = cleanup_stale_tmp()
    await _audit(session, admin, "cleanup", detail={"expired": expired, "freed": freed, "stale_tmp": stale})
    await session.commit()
    return {"expired": expired, "freed_bytes": freed, "stale_tmp": stale}


def _fp(token: str) -> str:
    if not token:
        return "not set"
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def get_tool_versions() -> dict:
    import subprocess

    def ver(cmd: list[str]) -> str:
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
            return (out.stdout or out.stderr).decode("utf-8", "replace").strip().splitlines()[0][:80]
        except (subprocess.SubprocessError, OSError, IndexError):
            return "unavailable"

    import os
    return {
        "yt_dlp": ver([os.getenv("YTDLP_BIN", "yt-dlp"), "--version"]),
        "gallery_dl": ver([os.getenv("GALLERYDL_BIN", "gallery-dl"), "--version"]),
        "ffmpeg": ver([os.getenv("FFMPEG_BIN", "ffmpeg"), "-version"]),
        "ffprobe": ver([os.getenv("FFPROBE_BIN", "ffprobe"), "-version"]),
    }
