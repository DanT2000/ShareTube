"""Job API: analyze, fetch, start download, cancel, retry, history, SSE progress."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user, rate_limit_guard
from ..models import DownloadJob, JobStatus, SelectedFormat, User
from ..queue import (
    enqueue_analyze,
    enqueue_download,
    get_last_progress,
    redis_settings,
    request_cancel,
)
from ..schemas import AnalyzeRequest, JobOut, StartDownloadRequest
from ..services import jobs as jobs_svc
from ..services.serialize import load_job, serialize_job

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/analyze", response_model=JobOut, dependencies=[Depends(rate_limit_guard)])
async def analyze(req: AnalyzeRequest, user: User = Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)):
    try:
        job = await jobs_svc.create_job(session, user_id=user.id, raw_url=req.url, origin="web")
    except jobs_svc.JobError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
    await session.commit()
    await enqueue_analyze(job.id)
    job = await load_job(session, job.id)
    return await serialize_job(session, job)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: User = Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)):
    job = await load_job(session, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return await serialize_job(session, job)


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session), limit: int = 20):
    rows = (await session.execute(
        select(DownloadJob).where(DownloadJob.user_id == user.id)
        .order_by(DownloadJob.created_at.desc()).limit(min(limit, 100))
    )).scalars().all()
    out = []
    for row in rows:
        j = await load_job(session, row.id)
        out.append(await serialize_job(session, j))
    return out


@router.post("/jobs/{job_id}/start", response_model=JobOut)
async def start_download(job_id: str, req: StartDownloadRequest,
                         user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    job = await load_job(session, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in (JobStatus.ANALYZED.value, JobStatus.FAILED.value):
        raise HTTPException(status_code=409, detail={"code": "bad_state",
                            "message": "Задание нельзя запустить в текущем статусе."})

    fmt = await _resolve_format(session, job, req)
    if fmt is None:
        raise HTTPException(status_code=400, detail={"code": "no_format",
                            "message": "Выбранный формат недоступен."})
    job.selected_format_id = fmt.id
    job.approx_size_bytes = fmt.approx_size_bytes
    if req.deliver_to_telegram:
        job.origin = "bot" if job.origin == "bot" else job.origin
    await jobs_svc.transition(session, job, JobStatus.QUEUED, stage="waiting", progress=0.0)
    await session.commit()
    await enqueue_download(job.id)
    job = await load_job(session, job.id)
    return await serialize_job(session, job)


async def _resolve_format(session, job, req) -> SelectedFormat | None:
    src = job.media_sources[0] if job.media_sources else None
    if not src:
        return None
    if req.format_id:
        return next((f for f in src.formats if f.id == req.format_id), None)
    if req.format_label:
        return next((f for f in src.formats if f.label == req.format_label), None)
    # default: auto
    return next((f for f in src.formats if f.label == "auto"), src.formats[0] if src.formats else None)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    job = await load_job(session, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    await request_cancel(job.id)
    if job.status in (JobStatus.PENDING.value, JobStatus.ANALYZED.value, JobStatus.QUEUED.value):
        job.error_code = "cancelled"
        await jobs_svc.transition(session, job, JobStatus.CANCELLED, stage="cancelled")
    await session.commit()
    return await serialize_job(session, job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: str, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    job = await load_job(session, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise HTTPException(status_code=409, detail="job is not finished")
    job.error_code = None
    job.error_message = None
    job.retry_count += 1
    if job.selected_format_id:
        await jobs_svc.transition(session, job, JobStatus.QUEUED, stage="waiting", progress=0.0)
        await session.commit()
        await enqueue_download(job.id)
    else:
        await jobs_svc.transition(session, job, JobStatus.PENDING, stage="analysis", progress=0.0)
        await session.commit()
        await enqueue_analyze(job.id)
    job = await load_job(session, job.id)
    return await serialize_job(session, job)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    """Server-Sent Events stream of progress for a job."""
    job = await load_job(session, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")

    import redis.asyncio as aioredis
    from ..config import settings as _s

    async def gen():
        last = await get_last_progress(job_id)
        if last:
            yield f"data: {json.dumps(last)}\n\n"
        r = aioredis.from_url(_s.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"progress:{job_id}")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg and msg.get("data"):
                    yield f"data: {msg['data']}\n\n"
                    data = json.loads(msg["data"])
                    if data.get("status") in ("done", "failed", "cancelled"):
                        break
                else:
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(f"progress:{job_id}")
            await r.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
