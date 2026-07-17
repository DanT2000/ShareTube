"""OutboundProfile abstraction — the only sanctioned network routes for downloads."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class ProfileCheckResult:
    ok: bool
    latency_ms: int | None = None
    exit_ip: str | None = None
    error_category: str | None = None
    sources_ok: dict[str, int] | None = None  # source -> http status


class OutboundProfile(abc.ABC):
    """A network route to public media sources (HTTP proxy or Xray tunnel)."""

    kind: str = "base"

    def __init__(self, profile_id: int, name: str):
        self.profile_id = profile_id
        self.name = name

    @abc.abstractmethod
    def proxy_url(self) -> str:
        """Return the proxy URL to hand to yt-dlp/gallery-dl/httpx (e.g. socks5h://…)."""
        ...

    @abc.abstractmethod
    async def check(self, test_url: str = "https://api.ipify.org") -> ProfileCheckResult:
        """Actively verify the route (DNS + TLS + exit IP + latency)."""
        ...

    def env(self) -> dict[str, str]:
        """Environment overrides (HTTP_PROXY/HTTPS_PROXY) for subprocess tools."""
        url = self.proxy_url()
        return {"HTTP_PROXY": url, "HTTPS_PROXY": url, "http_proxy": url, "https_proxy": url}
