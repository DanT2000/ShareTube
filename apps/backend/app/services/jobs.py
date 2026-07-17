"""Job lifecycle service: creation with quota/limit checks, dedup, state transitions."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..errors import user_message
from ..models import DownloadJob, JobStatus
from ..security.ssrf import UrlValidationError, validate_url

ACTIVE_STATUSES = (
    JobStatus.PENDING.value, JobStatus.ANALYZING.value, JobStatus.ANALYZED.value,
    JobStatus.QUEUED.value, JobStatus.DOWNLOADING.value, JobStatus.MERGING.value,
    JobStatus.CONVERTING.value, JobStatus.UPLOADING.value,
)


class JobError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.message = user_message(code)
        super().__init__(self.message)


def dedup_hash(user_id: int, normalized_url: str) -> str:
    return hashlib.sha256(f"{user_id}:{normalized_url}".encode()).hexdigest()


async def _count_active(session: AsyncSession, user_id: int) -> int:
    return (await session.execute(
        select(func.count()).select_from(DownloadJob).where(
            DownloadJob.user_id == user_id,
            DownloadJob.status.in_(ACTIVE_STATUSES),
        )
    )).scalar_one()


async def create_job(session: AsyncSession, *, user_id: int, raw_url: str,
                     origin: str = "web") -> DownloadJob:
    """Validate URL (SSRF) and create a PENDING job, enforcing per-user limits and dedup."""
    try:
        validated = validate_url(raw_url)
    except UrlValidationError as exc:
        raise JobError(exc.code if exc.code in _KNOWN else "unsupported") from exc

    # dedup: same user + same normalized url still active
    existing = (await session.execute(
        select(DownloadJob).where(
            DownloadJob.user_id == user_id,
            DownloadJob.normalized_url == validated.normalized,
            DownloadJob.status.in_(ACTIVE_STATUSES),
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        raise JobError("duplicate")

    active = await _count_active(session, user_id)
    if active >= settings.MAX_ACTIVE_JOBS_PER_USER + settings.MAX_QUEUED_JOBS_PER_USER:
        raise JobError("too_many_active")

    job = DownloadJob(
        user_id=user_id, origin=origin, original_url=validated.original,
        normalized_url=validated.normalized, status=JobStatus.PENDING.value,
    )
    session.add(job)
    await session.flush()
    return job


async def transition(session: AsyncSession, job: DownloadJob, status: JobStatus,
                     *, stage: str | None = None, progress: float | None = None) -> None:
    job.status = status.value
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = progress
    if status == JobStatus.DOWNLOADING and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
        job.finished_at = datetime.now(timezone.utc)
    job.heartbeat_at = datetime.now(timezone.utc)


async def fail_job(session: AsyncSession, job: DownloadJob, code: str,
                   message: str | None = None) -> None:
    job.error_code = code
    job.error_message = message or user_message(code)
    await transition(session, job, JobStatus.FAILED)


async def can_enqueue_download(session: AsyncSession, user_id: int) -> bool:
    """Global concurrency is enforced by the worker; here we cap per-user active downloads."""
    active_dl = (await session.execute(
        select(func.count()).select_from(DownloadJob).where(
            DownloadJob.user_id == user_id,
            DownloadJob.status.in_((JobStatus.DOWNLOADING.value, JobStatus.MERGING.value,
                                    JobStatus.CONVERTING.value, JobStatus.UPLOADING.value)),
        )
    )).scalar_one()
    return active_dl < settings.MAX_ACTIVE_JOBS_PER_USER


_KNOWN = {"empty", "too_long", "no_host", "scheme", "blocked_host", "private_ip",
          "denylist", "allowlist", "dns_error"}
