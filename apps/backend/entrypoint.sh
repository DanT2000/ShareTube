#!/bin/sh
# ShareTube container entrypoint. First arg selects the role.
set -e

ROLE="${1:-api}"

wait_for_db() {
    echo "[entrypoint] waiting for postgres…"
    python - <<'PY'
import time, sys
import psycopg2
from app.config import settings
dsn = settings.DATABASE_URL_SYNC.replace("+psycopg2", "")
for i in range(60):
    try:
        psycopg2.connect(dsn).close()
        print("[entrypoint] postgres is up")
        sys.exit(0)
    except Exception as e:
        time.sleep(2)
print("[entrypoint] postgres not reachable", file=sys.stderr)
sys.exit(1)
PY
}

case "$ROLE" in
    api)
        wait_for_db
        echo "[entrypoint] running migrations…"
        alembic upgrade head
        echo "[entrypoint] starting API on :8989"
        exec uvicorn app.main:app --host 0.0.0.0 --port 8989 --proxy-headers --forwarded-allow-ips='*'
        ;;
    worker)
        wait_for_db
        exec arq app.worker.WorkerSettings
        ;;
    bot)
        wait_for_db
        exec python -m app.tgbot
        ;;
    migrate)
        wait_for_db
        exec alembic upgrade head
        ;;
    *)
        exec "$@"
        ;;
esac
