#!/usr/bin/env bash
# Backup PostgreSQL + storage metadata. Does NOT back up secrets (.env) by design.
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT"

echo "[backup] dumping postgres…"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-sharetube}" "${POSTGRES_DB:-sharetube}" \
    | gzip > "$OUT/db_${STAMP}.sql.gz"

echo "[backup] archiving storage volume listing…"
docker compose exec -T app sh -c 'du -sh /data/storage 2>/dev/null' > "$OUT/storage_size_${STAMP}.txt" || true

echo "[backup] done -> $OUT/db_${STAMP}.sql.gz"
# retention: keep last 14
ls -1t "$OUT"/db_*.sql.gz | tail -n +15 | xargs -r rm -f
