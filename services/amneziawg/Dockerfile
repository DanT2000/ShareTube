# syntax=docker/dockerfile:1
# AmneziaWG (obfuscated WireGuard) userspace SOCKS5 gateway via wireproxy.
# Uses gVisor netstack — NO /dev/net/tun and NO NET_ADMIN required (works inside LXC).
# Downloader connects to socks5://amneziawg:1080; egress goes through the AmneziaWG tunnel.

FROM golang:1.25-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto
# wireproxy fork WITH real AmneziaWG obfuscation (Jc/Jmin/Jmax/S1/S2/H1-4).
RUN go install github.com/artem-russkikh/wireproxy-awg/cmd/wireproxy@latest \
    && cp /go/bin/wireproxy /out-wireproxy

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out-wireproxy /usr/bin/wireproxy
COPY services/amneziawg/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 1080
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD sh -c "exec 3<>/dev/tcp/127.0.0.1/1080" 2>/dev/null || exit 1
ENTRYPOINT ["/entrypoint.sh"]
