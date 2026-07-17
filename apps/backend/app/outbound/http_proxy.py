"""HTTP/HTTPS/SOCKS5 proxy outbound profile."""
from __future__ import annotations

import time

import httpx

from .base import OutboundProfile, ProfileCheckResult

_TEST_SOURCES = {
    "youtube": "https://www.youtube.com/robots.txt",
    "tiktok": "https://www.tiktok.com/robots.txt",
    "vk": "https://vk.com/robots.txt",
    "instagram": "https://www.instagram.com/robots.txt",
}


class HttpProxyProfile(OutboundProfile):
    kind = "http"

    def __init__(self, profile_id: int, name: str, url: str):
        super().__init__(profile_id, name)
        self._url = url  # full proxy url incl. auth (kept in memory only)

    def proxy_url(self) -> str:
        return self._url

    async def check(self, test_url: str = "https://api.ipify.org", *, check_sources: bool = True) -> ProfileCheckResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(proxy=self._url, timeout=25, follow_redirects=True) as client:
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
        except httpx.ProxyError:
            return ProfileCheckResult(ok=False, error_category="proxy_error")
        except httpx.ConnectTimeout:
            return ProfileCheckResult(ok=False, error_category="connect_timeout")
        except httpx.ConnectError:
            return ProfileCheckResult(ok=False, error_category="connect_error")
        except httpx.HTTPError as exc:
            return ProfileCheckResult(ok=False, error_category=type(exc).__name__)
