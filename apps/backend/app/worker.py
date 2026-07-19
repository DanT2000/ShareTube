"""ARQ downloader worker: analysis + download pipeline with limits, cancel, delivery."""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from arq import cron
from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .extractors import analyze_url
from .extractors.base import DownloadLimits, ExtractError
from .extractors.selector import get_extractor_by_name, get_extractor_chain
from .extractors.sources import detect_source
from .extractors.ytdlp import ffprobe_info
from .logging_config import get_logger
from .models import (
    CookieProfile,
    DownloadJob,
    JobStatus,
    MediaItem,
    MediaSource,
    SelectedFormat,
    TelegramFileCache,
)
from .outbound import manager as route_mgr
from .queue import (
    clear_cancel,
    is_cancel_requested,
    publish_progress,
    redis_settings,
)
from .security.crypto import decrypt
from .services import jobs as jobs_svc
from .services.delivery import chunk_album, decide_audio_delivery, decide_photo_group_delivery, decide_video_delivery
from .services.storage_service import cleanup_expired, cleanup_stale_tmp, enforce_storage_cap, register_stored_file, create_download_link

log = get_logger("worker")


# ---------- global concurrency semaphores (Redis) ----------
class RedisSemaphore:
    def __init__(self, redis: aioredis.Redis, key: str, limit: int, ttl: int = 7200):
        self.redis, self.key, self.limit, self.ttl = redis, key, limit, ttl
        self._token = os.urandom(8).hex()

    async def acquire(self) -> bool:
        n = await self.redis.incr(self.key)
        if n == 1:
            await self.redis.expire(self.key, self.ttl)
        if n > self.limit:
            await self.redis.decr(self.key)
            return False
        return True

    async def release(self):
        val = await self.redis.decr(self.key)
        if val < 0:
            await self.redis.set(self.key, 0)


async def _cookies_for(session, source: str) -> str | None:
    row = (await session.execute(
        select(CookieProfile).where(CookieProfile.source == source,
                                    CookieProfile.enabled.is_(True))
    )).scalar_one_or_none()
    if not row or not row.encrypted_data:
        return None
    data = decrypt(row.encrypted_data)
    if not data:
        return None
    fd, path = tempfile.mkstemp(prefix="ck_", suffix=".txt", dir=settings.TMP_DIR)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    return path


# ---------- analyze ----------
async def analyze_job(ctx, job_id: str) -> None:
    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
        if not job or job.status in (JobStatus.CANCELLED.value,):
            return
        source = detect_source(job.normalized_url)
        job.source = source
        await jobs_svc.transition(session, job, JobStatus.ANALYZING, stage="analysis", progress=0.0)
        await session.commit()
        await publish_progress(job_id, {"job_id": job_id, "status": "analyzing", "stage": "analysis"})

        cookies = None
        try:
            profile = await route_mgr.resolve_for_source(session, source)
            job.outbound_profile_id = profile.profile_id
            cookies = await _cookies_for(session, source)
            meta = await analyze_url(job.normalized_url, proxy_url=profile.proxy_url(),
                                     cookies_path=cookies)
        except route_mgr.NoRouteError:
            await jobs_svc.fail_job(session, job, "no_route")
            await session.commit()
            await publish_progress(job_id, {"job_id": job_id, "status": "failed",
                                            "error": job.error_message})
            return
        except ExtractError as exc:
            await jobs_svc.fail_job(session, job, exc.code, exc.message)
            await session.commit()
            await publish_progress(job_id, {"job_id": job_id, "status": "failed", "error": exc.message})
            return
        finally:
            if cookies:
                _safe_remove(cookies)

        # playlist gating
        if meta.content_type.value == "playlist" and not settings.PLAYLISTS_ENABLED:
            await jobs_svc.fail_job(session, job, "playlist_disabled")
            await session.commit()
            await publish_progress(job_id, {"job_id": job_id, "status": "failed", "error": job.error_message})
            return

        job.content_type = meta.content_type.value
        job.extractor = meta.extractor
        src = MediaSource(
            job_id=job.id, title=meta.title, author=meta.author, duration_sec=meta.duration_sec,
            thumbnail_url=meta.thumbnail_url, content_type=meta.content_type.value,
            item_count=meta.item_count, is_live=meta.is_live, raw_meta=meta.raw,
        )
        session.add(src)
        await session.flush()
        for f in meta.formats:
            session.add(SelectedFormat(
                source_id=src.id, label=f.label, format_selector=f.format_selector, ext=f.ext,
                vcodec=f.vcodec, acodec=f.acodec, width=f.width, height=f.height, fps=f.fps,
                approx_size_bytes=f.approx_size_bytes, size_is_estimate=f.size_is_estimate,
                audio_only=f.audio_only,
            ))
        for it in meta.items:
            session.add(MediaItem(source_id=src.id, position=it.position, kind=it.kind, url=it.url,
                                  filename=it.filename, width=it.width, height=it.height,
                                  duration_sec=it.duration_sec))
        # Auto-flow: bot jobs download immediately with the best "auto" format —
        # no quality picker, the user just gets the ready video.
        if job.deliver_to_telegram and not job.selected_format_id:
            fmts = (await session.execute(
                select(SelectedFormat).where(SelectedFormat.source_id == src.id)
            )).scalars().all()
            auto = next((f for f in fmts if f.label == "auto"), fmts[0] if fmts else None)
            if auto:
                job.selected_format_id = auto.id
                job.approx_size_bytes = auto.approx_size_bytes

        await jobs_svc.transition(session, job, JobStatus.ANALYZED, stage="analyzed", progress=0.0)
        await session.commit()
        await publish_progress(job_id, {"job_id": job_id, "status": "analyzed", "stage": "analyzed"})

        if job.deliver_to_telegram and job.selected_format_id:
            from .queue import enqueue_download
            await enqueue_download(job_id)


# ---------- download ----------
async def download_job(ctx, job_id: str) -> None:
    redis: aioredis.Redis = ctx["redis_raw"]
    dl_sema = RedisSemaphore(redis, "sema:downloads", settings.MAX_GLOBAL_DOWNLOADS)

    async with SessionLocal() as session:
        job = await session.get(DownloadJob, job_id)
        if not job or job.status == JobStatus.CANCELLED.value:
            return
        if await is_cancel_requested(job_id):
            await _mark_cancelled(session, job)
            return

    if not await dl_sema.acquire():
        # requeue shortly if global download slots are full
        from .queue import enqueue_download
        await enqueue_download(job_id)
        return

    work_dir = os.path.join(settings.TMP_DIR, f"job_{job_id}")
    cookies = None
    try:
        async with SessionLocal() as session:
            job = await session.get(DownloadJob, job_id)
            fmt = await session.get(SelectedFormat, job.selected_format_id) if job.selected_format_id else None
            if fmt is None:
                await jobs_svc.fail_job(session, job, "extract_failed", "Формат не выбран.")
                await session.commit()
                return
            source = job.source or detect_source(job.normalized_url)
            await jobs_svc.transition(session, job, JobStatus.DOWNLOADING, stage="downloading", progress=0.0)
            await session.commit()
            await publish_progress(job_id, {"job_id": job_id, "status": "downloading", "stage": "downloading"})

            try:
                profile = await route_mgr.resolve_for_source(session, source)
            except route_mgr.NoRouteError:
                await jobs_svc.fail_job(session, job, "no_route")
                await session.commit()
                await publish_progress(job_id, {"job_id": job_id, "status": "failed", "error": job.error_message})
                return

            cookies = await _cookies_for(session, source)
            fmt_obj = _fmt_to_dataclass(fmt)
            limits = DownloadLimits(
                max_bytes=settings.max_download_bytes,
                max_duration_sec=None,
                max_items=settings.MAX_PLAYLIST_ITEMS,
                timeout_sec=settings.JOB_TIMEOUT_MINUTES * 60,
                rate_limit_kbps=settings.DOWNLOAD_RATE_LIMIT_KBPS,
            )
            extractor_chain = get_extractor_chain(source, job.normalized_url)
            proxy = profile.proxy_url()
            failed_profile = profile.profile_id

        # progress publisher (outside session)
        import asyncio
        import time as _t
        last = {"t": 0.0}
        loop = asyncio.get_running_loop()
        _pending: set = set()

        def on_progress(d: dict):
            now = _t.monotonic()
            if now - last["t"] < 1.0 and d.get("status") == "downloading":
                return
            last["t"] = now
            total = d.get("total_bytes")
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100.0) if total else 0.0
            task = loop.create_task(publish_progress(job_id, {
                "job_id": job_id, "status": "downloading", "stage": "downloading",
                "progress": round(pct, 1), "downloaded_bytes": downloaded,
                "total_bytes": total, "speed": d.get("speed"), "eta": d.get("eta"),
            }))
            _pending.add(task)
            task.add_done_callback(_pending.discard)

        # download with failover through the extractor chain / routes
        result = None
        last_err: ExtractError | None = None
        for extractor in extractor_chain:
            if await is_cancel_requested(job_id):
                async with SessionLocal() as session:
                    job = await session.get(DownloadJob, job_id)
                    await _mark_cancelled(session, job)
                return
            try:
                result = await extractor.download(
                    job.normalized_url, work_dir=work_dir, fmt=fmt_obj, proxy_url=proxy,
                    cookies_path=cookies, progress=on_progress, limits=limits)
                break
            except ExtractError as exc:
                last_err = exc
                if exc.code in ("auth_required", "removed", "too_large", "cancelled"):
                    break
                # try a failover route once for network errors
                if exc.retriable:
                    try:
                        async with SessionLocal() as session:
                            profile = await route_mgr.failover_after_error(session, source, failed_profile)
                            proxy = profile.proxy_url()
                            failed_profile = profile.profile_id
                        result = await extractor.download(
                            job.normalized_url, work_dir=work_dir, fmt=fmt_obj, proxy_url=proxy,
                            cookies_path=cookies, progress=on_progress, limits=limits)
                        break
                    except (ExtractError, route_mgr.NoRouteError) as exc2:
                        last_err = exc2 if isinstance(exc2, ExtractError) else ExtractError("no_route", "Все маршруты недоступны.")
                continue

        if result is None:
            async with SessionLocal() as session:
                job = await session.get(DownloadJob, job_id)
                code = last_err.code if isinstance(last_err, ExtractError) else "extract_failed"
                msg = last_err.message if isinstance(last_err, ExtractError) else None
                await jobs_svc.fail_job(session, job, code, msg)
                await session.commit()
                await publish_progress(job_id, {"job_id": job_id, "status": "failed",
                                                "error": job.error_message})
            return

        # verify actual size + ffprobe
        actual = result.total_bytes
        primary = result.primary_path
        probe = ffprobe_info(primary) if primary else {}

        async with SessionLocal() as session:
            job = await session.get(DownloadJob, job_id)
            job.actual_size_bytes = actual
            await jobs_svc.transition(session, job, JobStatus.UPLOADING, stage="uploading", progress=100.0)
            await session.commit()
            await publish_progress(job_id, {"job_id": job_id, "status": "uploading", "stage": "uploading",
                                            "progress": 100.0})

            await _finalize_and_deliver(session, job, result, probe)
            await session.commit()

    except Exception as exc:  # noqa: BLE001 — worker must never crash silently
        log.error("download_job_error", job_id=job_id, error=str(exc), error_type=type(exc).__name__)
        async with SessionLocal() as session:
            job = await session.get(DownloadJob, job_id)
            if job and job.status not in (JobStatus.DONE.value, JobStatus.CANCELLED.value):
                await jobs_svc.fail_job(session, job, "internal")
                await session.commit()
                await publish_progress(job_id, {"job_id": job_id, "status": "failed",
                                                "error": job.error_message})
    finally:
        if cookies:
            _safe_remove(cookies)
        shutil.rmtree(work_dir, ignore_errors=True)
        await dl_sema.release()
        await clear_cancel(job_id)


async def _finalize_and_deliver(session, job: DownloadJob, result, probe: dict) -> None:
    from .models import ContentType
    ct = result.content_type
    primary = result.primary_path

    # photos / carousel / mixed -> keep as gallery
    if ct in (ContentType.PHOTO, ContentType.PHOTO_CAROUSEL, ContentType.MIXED) and len(result.files) >= 1:
        await _deliver_gallery(session, job, result)
        return

    # single video/audio
    filename = os.path.basename(primary)
    mime = "video/mp4" if ct == ContentType.VIDEO else ("audio/mpeg" if ct == ContentType.AUDIO else None)
    sf = await register_stored_file(session, job_id=job.id, src_path=primary, filename=filename,
                                    mime_type=mime)
    job.stored_file_id = sf.id
    await session.flush()

    if ct == ContentType.AUDIO:
        decision = decide_audio_delivery(sf.size_bytes)
    else:
        decision = decide_video_delivery(sf.size_bytes, vcodec=probe.get("vcodec"),
                                         acodec=probe.get("acodec"),
                                         ext=os.path.splitext(filename)[1].lstrip("."))
    job.delivery_method = decision.method.value

    # signed link always available
    link = await create_download_link(session, sf)
    await session.flush()

    if job.deliver_to_telegram and job.tg_chat_id:
        await _deliver_to_telegram(session, job, sf, decision, probe, link_token=link.token)

    await jobs_svc.transition(session, job, JobStatus.DONE, stage="done", progress=100.0)
    await publish_progress(job.id, {"job_id": job.id, "status": "done", "stage": "done",
                                    "download_url": f"{settings.PUBLIC_BASE_URL}/download/{link.token}"})


async def _deliver_gallery(session, job: DownloadJob, result) -> None:
    from .services import telegram_delivery as tg
    # store a zip for "download all"
    zip_path = os.path.join(os.path.dirname(result.files[0]), "gallery.zip")
    _make_zip(result.files, zip_path)
    sf = await register_stored_file(session, job_id=job.id, src_path=zip_path,
                                    filename=f"{job.source or 'gallery'}.zip",
                                    mime_type="application/zip", is_zip=True)
    job.stored_file_id = sf.id
    link = await create_download_link(session, sf)
    await session.flush()

    decision = decide_photo_group_delivery(result.total_bytes, len(result.files))
    job.delivery_method = decision.method.value

    if job.deliver_to_telegram and job.tg_chat_id:
        if decision.method.value in ("cloud_bot", "local_bot"):
            for group in chunk_album(result.files, 10):
                if len(group) == 1:
                    await tg.send_photo(job.tg_chat_id, group[0])
                else:
                    await tg.send_media_group(job.tg_chat_id, group)
        else:
            await tg.send_message(job.tg_chat_id,
                                  f"📦 Галерея слишком большая для альбома.\nСсылка на ZIP: "
                                  f"{settings.PUBLIC_BASE_URL}/download/{link.token}")
    await jobs_svc.transition(session, job, JobStatus.DONE, stage="done", progress=100.0)
    await publish_progress(job.id, {"job_id": job.id, "status": "done", "stage": "done",
                                    "download_url": f"{settings.PUBLIC_BASE_URL}/download/{link.token}"})


async def _deliver_to_telegram(session, job, sf, decision, probe, link_token) -> None:
    from .models import ContentType, DeliveryMethod, DeliveryAttempt
    from .services import telegram_delivery as tg

    chat_id = job.tg_chat_id
    caption = f"✅ Готово\nИсточник: {job.original_url}"
    local_path = None
    if sf.provider == "local":
        from .storage import get_storage_provider
        local_path = await get_storage_provider().local_path(sf.rel_path)

    # cached file_id reuse
    cache_key = _cache_key(job, sf)
    cached = (await session.execute(
        select(TelegramFileCache).where(TelegramFileCache.content_hash == cache_key)
    )).scalar_one_or_none()
    cached_id = cached.telegram_file_id if cached else None

    resp = None
    kind = "document"
    try:
        if decision.method in (DeliveryMethod.SIGNED_LINK, DeliveryMethod.ZIP_LINK):
            await tg.send_message(chat_id,
                                  f"📁 Файл слишком большой для Telegram.\nСкачать: "
                                  f"{settings.PUBLIC_BASE_URL}/download/{link_token}\n"
                                  f"Ссылка действует {settings.DOWNLOAD_LINK_TTL_HOURS} ч.")
            session.add(DeliveryAttempt(job_id=job.id, method=decision.method.value, success=True))
            job.telegram_file_id = None
            return
        if job.content_type == ContentType.AUDIO.value:
            kind = "audio"
            resp = await tg.send_audio(chat_id, local_path or "", caption=caption, cached_file_id=cached_id)
        else:
            kind = "video"
            resp = await tg.send_video(chat_id, local_path or "", caption=caption,
                                       streamable=not decision.as_document,
                                       width=probe.get("width"), height=probe.get("height"),
                                       duration=int(probe["duration"]) if probe.get("duration") else None,
                                       cached_file_id=cached_id)
        ok = bool(resp and resp.get("ok"))
        session.add(DeliveryAttempt(job_id=job.id, method=decision.method.value, success=ok,
                                    detail=None if ok else str(resp)[:500]))
        if ok:
            file_id = tg.extract_file_id(resp, kind)
            if file_id:
                job.telegram_file_id = file_id
                if not cached:
                    session.add(TelegramFileCache(content_hash=cache_key, delivery_kind=kind,
                                                  telegram_file_id=file_id, size_bytes=sf.size_bytes,
                                                  title=sf.filename))
        else:
            # delivery failed -> give the link as fallback
            await tg.send_message(chat_id,
                                  f"⚠️ Не удалось отправить файл в Telegram.\nСкачать: "
                                  f"{settings.PUBLIC_BASE_URL}/download/{link_token}")
    except Exception as exc:  # noqa: BLE001
        log.error("tg_deliver_error", job_id=job.id, error=str(exc))
        session.add(DeliveryAttempt(job_id=job.id, method=decision.method.value, success=False,
                                    detail=str(exc)[:500]))
        await tg.send_message(chat_id,
                              f"⚠️ Ошибка отправки. Скачать по ссылке: "
                              f"{settings.PUBLIC_BASE_URL}/download/{link_token}")


def _cache_key(job, sf) -> str:
    import hashlib
    return hashlib.sha256(f"{job.normalized_url}|{job.selected_format_id}|{sf.size_bytes}".encode()).hexdigest()


def _fmt_to_dataclass(fmt: SelectedFormat):
    from .extractors.base import Format
    return Format(label=fmt.label, format_selector=fmt.format_selector, ext=fmt.ext,
                  vcodec=fmt.vcodec, acodec=fmt.acodec, width=fmt.width, height=fmt.height,
                  fps=fmt.fps, approx_size_bytes=fmt.approx_size_bytes,
                  size_is_estimate=fmt.size_is_estimate, audio_only=fmt.audio_only)


async def _mark_cancelled(session, job) -> None:
    job.error_code = "cancelled"
    await jobs_svc.transition(session, job, JobStatus.CANCELLED, stage="cancelled")
    await session.commit()
    await publish_progress(job.id, {"job_id": job.id, "status": "cancelled"})


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _make_zip(files: list[str], dest: str) -> None:
    import zipfile
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as zf:
        for i, f in enumerate(files):
            zf.write(f, arcname=f"{i+1:02d}_{os.path.basename(f)}")


# ---------- cron maintenance ----------
async def cleanup_cron(ctx) -> None:
    async with SessionLocal() as session:
        expired = await cleanup_expired(session)
        freed = await enforce_storage_cap(session)
        await session.commit()
    stale = cleanup_stale_tmp()
    log.info("cleanup_cron", expired=expired, freed=freed, stale_tmp=stale)


async def recover_stale_cron(ctx) -> None:
    """Recover jobs orphaned by a worker restart/crash.

    - Downloading/merging/converting/uploading past the job timeout -> failed(timeout).
    - Stuck in pending/analyzing/queued with no heartbeat for >10 min -> failed(timeout),
      so a stale job never permanently blocks re-submission of the same link (dedup).
    """
    now = datetime.now(timezone.utc)
    dl_cutoff = now - timedelta(minutes=settings.JOB_TIMEOUT_MINUTES + 5)
    early_cutoff = now - timedelta(minutes=10)
    active_late = [JobStatus.DOWNLOADING.value, JobStatus.MERGING.value,
                   JobStatus.CONVERTING.value, JobStatus.UPLOADING.value]
    early = [JobStatus.PENDING.value, JobStatus.ANALYZING.value, JobStatus.QUEUED.value]
    async with SessionLocal() as session:
        late_rows = (await session.execute(
            select(DownloadJob).where(
                DownloadJob.status.in_(active_late),
                DownloadJob.started_at < dl_cutoff)
        )).scalars().all()
        early_rows = (await session.execute(
            select(DownloadJob).where(
                DownloadJob.status.in_(early),
                func.coalesce(DownloadJob.heartbeat_at, DownloadJob.created_at) < early_cutoff)
        )).scalars().all()
        for job in [*late_rows, *early_rows]:
            await jobs_svc.fail_job(session, job, "timeout")
        if late_rows or early_rows:
            log.info("recover_stale", late=len(late_rows), early=len(early_rows))
        await session.commit()


async def _startup(ctx):
    ctx["redis_raw"] = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _shutdown(ctx):
    await ctx["redis_raw"].aclose()


class WorkerSettings:
    functions = [analyze_job, download_job]
    cron_jobs = [
        cron(cleanup_cron, minute=set(range(0, 60, 15))),
        cron(recover_stale_cron, minute=set(range(0, 60, 5))),
    ]
    on_startup = _startup
    on_shutdown = _shutdown
    redis_settings = redis_settings()
    max_jobs = settings.MAX_GLOBAL_DOWNLOADS + 2
    job_timeout = settings.JOB_TIMEOUT_MINUTES * 60 + 120
    keep_result = 3600
