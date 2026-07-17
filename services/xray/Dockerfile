# syntax=docker/dockerfile:1
# Xray sidecar: parses an outbound URI at start and exposes local SOCKS5/HTTP inbounds.
FROM ghcr.io/xtls/xray-core:latest AS xraybin

FROM python:3.12-slim
COPY --from=xraybin /usr/local/bin/xray /usr/local/bin/xray
# geo data for routing rules (geoip:private)
COPY --from=xraybin /usr/local/share/xray/ /usr/local/share/xray/
WORKDIR /opt/xray
COPY services/xray/generate_config.py ./generate_config.py
COPY services/xray/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
EXPOSE 1080 1081
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import socket;socket.create_connection(('127.0.0.1',1080),3)" || exit 1
ENTRYPOINT ["./entrypoint.sh"]
