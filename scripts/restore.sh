#!/usr/bin/env bash
# Restore PostgreSQL from a gzipped dump produced by backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DUMP="${1:?usage: restore.sh <db_dump.sql.gz>}"
[ -f "$DUMP" ] || { echo "file not found: $DUMP"; exit 1; }

echo "[restore] WARNING: this overwrites the current database."
read -r -p "Type 'yes' to continue: " confirm
[ "$confirm" = "yes" ] || { echo "aborted"; exit 1; }

echo "[restore] restoring $DUMP…"
gunzip -c "$DUMP" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-sharetube}" "${POSTGRES_DB:-sharetube}"
echo "[restore] applying migrations…"
docker compose run --rm app migrate
echo "[restore] done."
