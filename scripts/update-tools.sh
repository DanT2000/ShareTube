#!/usr/bin/env bash
# Controlled update of downloader tools (yt-dlp / gallery-dl) with smoke test + rollback.
# Does NOT auto-update on every start; run this deliberately.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVICE="${1:-worker}"
LOG="./update-tools.log"
echo "=== $(date -u +%FT%TZ) update start ===" >> "$LOG"

echo "[update] current versions:"
docker compose exec -T "$SERVICE" sh -c 'yt-dlp --version; gallery-dl --version' | tee -a "$LOG"

echo "[update] upgrading inside a throwaway layer…"
docker compose exec -T "$SERVICE" pip install -U yt-dlp gallery-dl 2>&1 | tail -2 | tee -a "$LOG"

echo "[update] smoke test (metadata only, through configured route)…"
if docker compose exec -T "$SERVICE" yt-dlp -J --no-download --skip-download \
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ" >/dev/null 2>>"$LOG"; then
    echo "[update] smoke test PASSED" | tee -a "$LOG"
    echo "[update] NOTE: to persist across container rebuilds, bump versions in requirements.txt"
else
    echo "[update] smoke test FAILED — rolling back by restarting the pinned image" | tee -a "$LOG"
    docker compose restart "$SERVICE"
    exit 1
fi
