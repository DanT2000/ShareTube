# syntax=docker/dockerfile:1

# ---------- stage 1: build frontend ----------
FROM node:20-slim AS frontend
WORKDIR /fe
COPY apps/frontend/package.json apps/frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY apps/frontend/ ./
RUN npm run build

# ---------- stage 2: python runtime ----------
FROM python:3.12-slim AS runtime

# Deno JS runtime — required by recent yt-dlp to solve YouTube's player (nsig)
# challenge; without it YouTube returns no formats.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# system deps: ffmpeg/ffprobe for post-processing
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
# yt-dlp PO-token plugin (talks to the bgutil pot-provider service) — bypasses the
# YouTube datacenter-IP "no formats" bot-check.
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

COPY apps/backend/app ./app
COPY apps/backend/alembic.ini ./alembic.ini
COPY apps/backend/migrations ./migrations
COPY apps/backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# built frontend served by FastAPI
COPY --from=frontend /fe/dist ./frontend
ENV FRONTEND_DIST=/app/frontend

# record tool versions at build time (shown in admin; not auto-updated at runtime)
RUN yt-dlp --version > /app/.tool_versions 2>/dev/null || true

EXPOSE 8989
ENTRYPOINT ["/usr/bin/tini", "--", "./entrypoint.sh"]
CMD ["api"]
