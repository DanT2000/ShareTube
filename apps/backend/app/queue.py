"""ARQ queue integration and Redis progress pub/sub."""
from __future__ import annotations

import json

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from .config import settings

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue_analyze(job_id: str) -> None:
    pool = await get_pool()
    await pool.enqueue_job("analyze_job", job_id, _job_id=f"analyze:{job_id}")


async def enqueue_download(job_id: str) -> None:
    pool = await get_pool()
    await pool.enqueue_job("download_job", job_id, _job_id=f"download:{job_id}")


# --- progress pub/sub ---
def _progress_channel(job_id: str) -> str:
    return f"progress:{job_id}"


async def publish_progress(job_id: str, payload: dict) -> None:
    pool = await get_pool()
    data = json.dumps(payload)
    await pool.publish(_progress_channel(job_id), data)
    # also keep last state for late subscribers / polling
    await pool.set(f"progress_last:{job_id}", data, ex=3600)


async def get_last_progress(job_id: str) -> dict | None:
    pool = await get_pool()
    raw = await pool.get(f"progress_last:{job_id}")
    return json.loads(raw) if raw else None


# --- cancellation flag ---
async def request_cancel(job_id: str) -> None:
    pool = await get_pool()
    await pool.set(f"cancel:{job_id}", "1", ex=7200)


async def is_cancel_requested(job_id: str) -> bool:
    pool = await get_pool()
    return bool(await pool.get(f"cancel:{job_id}"))


async def clear_cancel(job_id: str) -> None:
    pool = await get_pool()
    await pool.delete(f"cancel:{job_id}")
