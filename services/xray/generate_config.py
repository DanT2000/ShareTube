#!/usr/bin/env python3
"""Generate Xray client config from an outbound URI or raw JSON, at container start.

Reads the secret from env (XRAY_OUTBOUND_URI or XRAY_CONFIG_JSON) — never from git.
Exposes SOCKS5 :1080 and HTTP :1081 inbounds (internal Docker network only).
Blocks routing to private IPs through the tunnel.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import parse_qs, urlsplit

OUT = "/etc/xray/config.json"


def from_vless(uri: str) -> dict:
    u = urlsplit(uri)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    stream = {"network": q.get("type", "tcp"), "security": q.get("security", "none")}
    if q.get("security") == "reality":
        stream["realitySettings"] = {
            "publicKey": q.get("pbk", ""), "fingerprint": q.get("fp", "chrome"),
            "serverName": q.get("sni", ""), "shortId": q.get("sid", ""),
            "spiderX": q.get("spx", "/"),
        }
    elif q.get("security") == "tls":
        stream["tlsSettings"] = {"serverName": q.get("sni", u.hostname or ""),
                                 "fingerprint": q.get("fp", "chrome")}
    return {
        "protocol": "vless",
        "settings": {"vnext": [{"address": u.hostname, "port": u.port or 443,
                     "users": [{"id": u.username, "encryption": q.get("encryption", "none"),
                                "flow": q.get("flow", "")}]}]},
        "streamSettings": stream,
        "tag": "proxy",
    }


def build(outbound: dict) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks-in", "listen": "0.0.0.0", "port": 1080, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True}},
            {"tag": "http-in", "listen": "0.0.0.0", "port": 1081, "protocol": "http", "settings": {}},
        ],
        "outbounds": [outbound,
                      {"tag": "direct", "protocol": "freedom"},
                      {"tag": "block", "protocol": "blackhole"}],
        "routing": {"rules": [{"type": "field", "ip": ["geoip:private"], "outboundTag": "block"}]},
    }


def main() -> int:
    raw_json = os.getenv("XRAY_CONFIG_JSON", "").strip()
    uri = os.getenv("XRAY_OUTBOUND_URI", "").strip()
    os.makedirs("/etc/xray", exist_ok=True)
    if raw_json:
        cfg = json.loads(raw_json)
    elif uri.startswith("vless://"):
        cfg = build(from_vless(uri))
    else:
        print("ERROR: set XRAY_OUTBOUND_URI (vless://…) or XRAY_CONFIG_JSON", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump(cfg, f, indent=2)
    # Do not print secrets. Only confirm.
    print(f"[xray] config written to {OUT} ({len(cfg.get('outbounds', []))} outbounds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
