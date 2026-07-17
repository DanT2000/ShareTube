#!/bin/sh
set -e
python3 /opt/xray/generate_config.py
echo "[xray] starting core…"
exec xray run -c /etc/xray/config.json
