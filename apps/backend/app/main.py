"""ShareTube FastAPI application entrypoint."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .logging_config import configure_logging, get_logger
from .routers import admin, auth, download, health, jobs

configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.0,
                        environment=settings.ENV, send_default_pii=False)
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    os.makedirs(settings.TMP_DIR, exist_ok=True)
    # seed a default outbound profile so downloads are routed out of the box
    try:
        from .db import SessionLocal
        from .outbound.manager import ensure_seed_profile
        async with SessionLocal() as session:
            await ensure_seed_profile(session)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — never block startup on seeding
        log.warning("seed_profile_failed", error=str(exc))
    log.info("startup", version=__version__, env=settings.ENV)
    yield
    log.info("shutdown")


app = FastAPI(title="ShareTube", version=__version__, lifespan=lifespan,
              docs_url="/api/docs" if settings.ENV != "prod" else None,
              redoc_url=None, openapi_url="/api/openapi.json" if settings.ENV != "prod" else None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:16])
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    # basic security headers
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled_error", error=str(exc), error_type=type(exc).__name__)
    return JSONResponse(status_code=500,
                        content={"detail": {"code": "internal",
                                            "message": "Внутренняя ошибка. Попробуйте позже."}})


for r in (health.router, auth.router, jobs.router, admin.router, download.router):
    app.include_router(r)

if settings.PROMETHEUS_ENABLED:
    from prometheus_client import make_asgi_app
    app.mount("/metrics", make_asgi_app())


# --- serve built frontend (SPA) if present ---
_FRONTEND_DIR = os.getenv("FRONTEND_DIST", "/app/frontend")
if os.path.isdir(_FRONTEND_DIR):
    assets_dir = os.path.join(_FRONTEND_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        # never shadow API/health/download routes (handled above by ordering)
        candidate = os.path.join(_FRONTEND_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(_FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "not found"})
