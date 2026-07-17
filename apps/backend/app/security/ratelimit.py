"""Redis-backed sliding-window rate limiting and brute-force protection."""
from __future__ import annotations

import time

import redis.asyncio as aioredis

from ..config import settings

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def check_rate_limit(key: str, limit: int | None = None, window: int = 60) -> bool:
    """Return True if allowed, False if over the limit. Fixed-window counter."""
    limit = limit or settings.RATE_LIMIT_PER_MINUTE
    r = _client()
    bucket = f"rl:{key}:{int(time.time() // window)}"
    count = await r.incr(bucket)
    if count == 1:
        await r.expire(bucket, window * 2)
    return count <= limit


async def register_failure(key: str, window: int = 300) -> int:
    """Track failed attempts (e.g. link brute-force / admin login). Returns count."""
    r = _client()
    bucket = f"bf:{key}"
    count = await r.incr(bucket)
    if count == 1:
        await r.expire(bucket, window)
    return count


async def is_locked_out(key: str, threshold: int = 10) -> bool:
    r = _client()
    val = await r.get(f"bf:{key}")
    return bool(val) and int(val) >= threshold
