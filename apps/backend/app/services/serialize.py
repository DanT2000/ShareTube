"""Serialize ORM jobs into API JobOut, hiding internal fields."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import DownloadJob, MediaSource, SelectedFormat, StoredFile
from ..schemas import FormatOut, JobOut, MediaItemOut


async def load_job(session: AsyncSession, job_id: str) -> DownloadJob | None:
    return (await session.execute(
        select(DownloadJob)
        .where(DownloadJob.id == job_id)
        .options(
            selectinload(DownloadJob.media_sources).selectinload(MediaSource.formats),
            selectinload(DownloadJob.media_sources).selectinload(MediaSource.items),
        )
    )).scalar_one_or_none()


async def serialize_job(session: AsyncSession, job: DownloadJob) -> JobOut:
    src = job.media_sources[0] if job.media_sources else None
    formats: list[FormatOut] = []
    items: list[MediaItemOut] = []
    if src:
        for f in sorted(src.formats, key=lambda x: (x.height or 0), reverse=True):
            formats.append(FormatOut(
                id=f.id, label=f.label, ext=f.ext, vcodec=f.vcodec, acodec=f.acodec,
                width=f.width, height=f.height, fps=f.fps,
                approx_size_bytes=f.approx_size_bytes, size_is_estimate=f.size_is_estimate,
                audio_only=f.audio_only,
            ))
        for it in sorted(src.items, key=lambda x: x.position):
            items.append(MediaItemOut(position=it.position, kind=it.kind, filename=it.filename,
                                      width=it.width, height=it.height))

    download_url = None
    if job.stored_file_id:
        sf = await session.get(StoredFile, job.stored_file_id)
        if sf and not sf.deleted_at:
            from ..models import DownloadLink
            link = (await session.execute(
                select(DownloadLink).where(DownloadLink.stored_file_id == sf.id,
                                           DownloadLink.revoked.is_(False))
                .order_by(DownloadLink.created_at.desc()).limit(1)
            )).scalar_one_or_none()
            if link:
                download_url = f"{settings.PUBLIC_BASE_URL}/download/{link.token}"

    return JobOut(
        id=job.id, status=job.status, stage=job.stage, progress=job.progress,
        source=job.source, content_type=job.content_type,
        original_url=job.original_url, normalized_url=job.normalized_url,
        title=src.title if src else None, author=src.author if src else None,
        duration_sec=src.duration_sec if src else None,
        thumbnail_url=src.thumbnail_url if src else None,
        item_count=src.item_count if src else 1,
        approx_size_bytes=job.approx_size_bytes, actual_size_bytes=job.actual_size_bytes,
        error_code=job.error_code, error_message=job.error_message,
        delivery_method=job.delivery_method, download_url=download_url,
        telegram_file_id=job.telegram_file_id, formats=formats, items=items,
        created_at=job.created_at, finished_at=job.finished_at,
    )
