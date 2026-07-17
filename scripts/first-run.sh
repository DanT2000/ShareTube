#!/usr/bin/env bash
# First-time setup: create .env from example, generate secrets, build and start the stack.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "[first-run] creating .env from .env.example"
    cp .env.example .env
    SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
    PGPASS=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
    sed -i "s|change_me_strong_password|${PGPASS}|g" .env
    echo "[first-run] .env created. Edit BOT_TOKEN, TELEGRAM_ADMIN_IDS, XRAY_OUTBOUND_URI now."
    echo "[first-run] then re-run this script."
    exit 0
fi

echo "[first-run] building images…"
docker compose build

echo "[first-run] starting core services…"
docker compose up -d postgres redis xray

echo "[first-run] running migrations…"
docker compose run --rm app migrate

echo "[first-run] starting app, worker, bot…"
docker compose up -d app worker bot

echo "[first-run] done. Health:"
sleep 5
docker compose ps
curl -fsS "http://localhost:${APP_PORT:-8989}/health" && echo " OK" || echo " (health not ready yet)"
