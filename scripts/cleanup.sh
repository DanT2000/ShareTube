#!/usr/bin/env bash
# Trigger storage cleanup: expired links, over-cap eviction, stale temp dirs.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T app python - <<'PY'
import asyncio
from app.db import SessionLocal
from app.services.storage_service import cleanup_expired, cleanup_stale_tmp, enforce_storage_cap

async def main():
    async with SessionLocal() as s:
        e = await cleanup_expired(s)
        f = await enforce_storage_cap(s)
        await s.commit()
    t = cleanup_stale_tmp()
    print(f"expired={e} freed_bytes={f} stale_tmp={t}")

asyncio.run(main())
PY
