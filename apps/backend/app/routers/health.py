"""Health and readiness endpoints (safe — no secrets)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from .. import __version__
from ..config import settings
from ..db import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "version": __version__, "env": settings.ENV}


@router.get("/health/ready")
async def ready():
    checks = {"db": False, "redis": False}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        pass
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = True
    except Exception:
        pass
    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks}
