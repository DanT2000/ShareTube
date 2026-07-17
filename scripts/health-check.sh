#!/usr/bin/env bash
# Quick health probe of all ShareTube services.
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${APP_PORT:-8989}"

echo "== containers =="
docker compose ps

echo "== app /health =="
curl -fsS "http://localhost:${PORT}/health" && echo || echo "APP DOWN"

echo "== app /health/ready =="
curl -fsS "http://localhost:${PORT}/health/ready" && echo || echo "NOT READY"

echo "== redis =="
docker compose exec -T redis redis-cli ping || echo "REDIS DOWN"

echo "== postgres =="
docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-sharetube}" || echo "PG DOWN"

echo "== xray socks =="
docker compose exec -T worker python -c "import socket;socket.create_connection(('xray',1080),3);print('xray reachable')" || echo "XRAY DOWN"
