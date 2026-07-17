"""Xray outbound profile — downloader connects to Xray's local SOCKS5 inbound.

The Xray process runs as a separate container; this profile just points tools at
its SOCKS inbound and can validate config JSON before it is applied.
"""
from __future__ import annotations

import json
import time

import httpx

from ..config import settings
from .base import OutboundProfile, ProfileCheckResult
from .http_proxy import _TEST_SOURCES


class XrayProfile(OutboundProfile):
    kind = "xray"

    def __init__(self, profile_id: int, name: str, socks_url: str | None = None):
        super().__init__(profile_id, name)
        self._socks = socks_url or settings.XRAY_SOCKS_URL

    def proxy_url(self) -> str:
        return self._socks

    async def check(self, test_url: str = "https://api.ipify.org", *, check_sources: bool = True) -> ProfileCheckResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(proxy=self._socks, timeout=25, follow_redirects=True) as client:
                resp = await client.get(test_url)
                latency = int((time.perf_counter() - t0) * 1000)
                exit_ip = resp.text.strip()[:64] if resp.status_code == 200 else None
                sources: dict[str, int] = {}
                if check_sources:
                    for src, url in _TEST_SOURCES.items():
                        try:
                            r = await client.get(url, timeout=20)
                            sources[src] = r.status_code
                        except httpx.HTTPError:
                            sources[src] = 0
                return ProfileCheckResult(ok=resp.status_code == 200, latency_ms=latency,
                                          exit_ip=exit_ip, sources_ok=sources)
        except httpx.HTTPError as exc:
            return ProfileCheckResult(ok=False, error_category=type(exc).__name__)


def validate_xray_config(raw: str) -> tuple[bool, str]:
    """Validate that raw is well-formed Xray JSON with outbounds. Returns (ok, message)."""
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as exc:
        return False, f"invalid json: {exc.msg}"
    if not isinstance(cfg, dict):
        return False, "config must be an object"
    if not cfg.get("outbounds"):
        return False, "no outbounds defined"
    if not cfg.get("inbounds"):
        return False, "no inbounds defined"
    return True, "ok"
