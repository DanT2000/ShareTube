"""Storage lifecycle: register files, enforce total-size cap, TTL cleanup, stale tmp."""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..logging_config import get_logger
from ..models import DownloadLink, StoredFile
from ..storage import get_storage_provider

log = get_logger("storage")


async def register_stored_file(
    session: AsyncSession, *, job_id: str | None, src_path: str, filename: str,
    mime_type: str | None, is_zip: bool = False,
) -> StoredFile:
    provider = get_storage_provider()
    obj = await provider.save(src_path, filename, mime_type=mime_type)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.DOWNLOAD_LINK_TTL_HOURS)
    sf = StoredFile(
        job_id=job_id, provider=obj.provider, rel_path=obj.rel_path, filename=obj.filename,
        mime_type=obj.mime_type, size_bytes=obj.size_bytes, is_zip=is_zip, expires_at=expires,
    )
    session.add(sf)
    await session.flush()
    await enforce_storage_cap(session)
    return sf


async def create_download_link(session: AsyncSession, stored_file: StoredFile,
                               ttl_hours: int | None = None,
                               max_downloads: int | None = None) -> DownloadLink:
    ttl = ttl_hours if ttl_hours is not None else settings.DOWNLOAD_LINK_TTL_HOURS
    link = DownloadLink(
        stored_file_id=stored_file.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl),
        max_downloads=max_downloads,
    )
    session.add(link)
    await session.flush()
    return link


async def enforce_storage_cap(session: AsyncSession) -> int:
    """Delete oldest completed files until total under MAX_STORAGE_GB. Returns freed bytes."""
    provider = get_storage_provider()
    rows = (await session.execute(
        select(StoredFile).where(StoredFile.deleted_at.is_(None)).order_by(StoredFile.created_at.asc())
    )).scalars().all()
    total = sum(r.size_bytes for r in rows)
    cap = settings.max_storage_bytes
    freed = 0
    for sf in rows:
        if total <= cap:
            break
        await provider.delete(sf.rel_path)
        sf.deleted_at = datetime.now(timezone.utc)
        total -= sf.size_bytes
        freed += sf.size_bytes
        log.info("storage_evict", stored_file_id=sf.id, size=sf.size_bytes)
    return freed


async def cleanup_expired(session: AsyncSession) -> int:
    """Delete files past TTL. Returns count deleted."""
    provider = get_storage_provider()
    now = datetime.now(timezone.utc)
    rows = (await session.execute(
        select(StoredFile).where(StoredFile.deleted_at.is_(None), StoredFile.expires_at < now)
    )).scalars().all()
    n = 0
    for sf in rows:
        await provider.delete(sf.rel_path)
        sf.deleted_at = now
        n += 1
    if rows:
        await session.execute(
            update(DownloadLink)
            .where(DownloadLink.stored_file_id.in_([r.id for r in rows]))
            .values(revoked=True)
        )
    return n


def cleanup_stale_tmp(max_age_hours: int = 6) -> int:
    """Remove orphaned per-job temp dirs older than max_age_hours. Returns count."""
    tmp = settings.TMP_DIR
    if not os.path.isdir(tmp):
        return 0
    cutoff = time.time() - max_age_hours * 3600
    n = 0
    for entry in os.listdir(tmp):
        path = os.path.join(tmp, entry)
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
                n += 1
        except OSError:
            continue
    return n
