#!/usr/bin/env bash
# Rebuild and roll out the stack (used on the server / by Coolify hook).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[deploy] pulling base images & building…"
docker compose build

echo "[deploy] running migrations…"
docker compose up -d postgres redis
docker compose run --rm app migrate

echo "[deploy] restarting services…"
docker compose up -d --remove-orphans

echo "[deploy] waiting for health…"
for i in $(seq 1 30); do
    if curl -fsS "http://localhost:${APP_PORT:-8989}/health" >/dev/null 2>&1; then
        echo "[deploy] healthy."
        docker compose ps
        exit 0
    fi
    sleep 3
done
echo "[deploy] WARNING: health check did not pass in time" >&2
docker compose ps
exit 1
