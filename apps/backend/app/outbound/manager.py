"""Route manager: resolves which OutboundProfile a job must use.

Enforces the core policy: downloads go ONLY through configured routes.
`proxy failed` never means `try direct`. If no route is usable -> NO_ROUTE error.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..logging_config import get_logger
from ..models import ProxyProfile
from ..security.crypto import decrypt, encrypt
from .base import OutboundProfile
from .http_proxy import HttpProxyProfile
from .xray import XrayProfile

log = get_logger("outbound")


class NoRouteError(Exception):
    """Raised when no configured outbound route is available."""


def _build_profile(row: ProxyProfile) -> OutboundProfile | None:
    if row.kind == "xray":
        return XrayProfile(row.id, row.name, settings.XRAY_SOCKS_URL)
    cfg = decrypt(row.encrypted_config)
    if not cfg:
        return None
    return HttpProxyProfile(row.id, row.name, cfg)


def _mask_proxy_url(url: str) -> dict:
    """Produce safe display metadata for a proxy URL (no password, masked host/port)."""
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        masked_host = (host[:3] + "***" + host[-3:]) if len(host) > 6 else "***"
        port = str(p.port or "")
        masked_port = ("**" + port[-2:]) if len(port) >= 2 else "***"
        return {"protocol": p.scheme, "host": masked_host, "port": masked_port,
                "has_auth": bool(p.username)}
    except ValueError:
        return {"protocol": "unknown", "host": "***", "port": "***", "has_auth": False}


async def list_profiles(session: AsyncSession) -> list[ProxyProfile]:
    return (await session.execute(
        select(ProxyProfile).order_by(ProxyProfile.priority.asc(), ProxyProfile.id.asc())
    )).scalars().all()


async def resolve_for_source(session: AsyncSession, source: str | None,
                             *, disable_proxy: bool = False) -> OutboundProfile:
    """Pick the outbound profile for a source. Prefers source-bound, then primary,
    then any enabled ok profile, then backup. Raises NoRouteError if none.
    """
    if disable_proxy and not settings.OUTBOUND_REQUIRED:
        raise NoRouteError("direct disabled by policy")

    rows = [r for r in await list_profiles(session) if r.enabled]
    if not rows:
        raise NoRouteError("no outbound profiles configured")

    def bound_match(r: ProxyProfile) -> bool:
        if not r.bound_sources:
            return False
        return source is not None and source in {s.strip() for s in r.bound_sources.split(",")}

    # Ordering: bound-to-source first, then primary, then healthy, then backup, then rest.
    ordered = sorted(
        rows,
        key=lambda r: (
            0 if bound_match(r) else 1,
            0 if r.is_primary else 1,
            0 if r.last_status == "ok" else 1,
            0 if r.is_backup else 1,
            r.priority,
        ),
    )
    for row in ordered:
        prof = _build_profile(row)
        if prof is not None:
            log.info("route_selected", profile=row.name, kind=row.kind, source=source)
            return prof
    raise NoRouteError("no usable outbound profile")


async def failover_after_error(session: AsyncSession, source: str | None,
                               failed_profile_id: int) -> OutboundProfile:
    """After a route error, select the next best profile excluding the failed one."""
    rows = [r for r in await list_profiles(session)
            if r.enabled and r.id != failed_profile_id]
    if not rows:
        raise NoRouteError("no backup route available")
    ordered = sorted(rows, key=lambda r: (0 if r.is_backup else 1,
                                          0 if r.last_status == "ok" else 1, r.priority))
    for row in ordered:
        prof = _build_profile(row)
        if prof is not None:
            log.info("route_failover", to=row.name, from_id=failed_profile_id)
            return prof
    raise NoRouteError("no backup route available")


async def create_http_profile(session: AsyncSession, name: str, url: str, **kw) -> ProxyProfile:
    row = ProxyProfile(
        name=name, kind="socks5" if url.startswith("socks") else "http",
        encrypted_config=encrypt(url), display_meta=_mask_proxy_url(url), **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def create_xray_profile(session: AsyncSession, name: str, config_or_uri: str, **kw) -> ProxyProfile:
    row = ProxyProfile(
        name=name, kind="xray", encrypted_config=encrypt(config_or_uri),
        display_meta={"protocol": "xray", "host": "***", "port": "***", "has_auth": True}, **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def ensure_seed_profile(session: AsyncSession) -> None:
    """On first start, create a default Xray outbound profile if none exist and an
    Xray route is configured. Keeps downloads routed without manual admin setup.
    """
    existing = (await session.execute(select(ProxyProfile).limit(1))).scalar_one_or_none()
    if existing is not None:
        return
    if not settings.XRAY_SOCKS_URL:
        return
    row = ProxyProfile(
        name="xray-main", kind="xray", enabled=True, is_primary=True, priority=10,
        encrypted_config=encrypt(settings.XRAY_SOCKS_URL),
        display_meta={"protocol": "xray", "host": "xray", "port": "1080", "has_auth": False},
        last_status="unknown",
    )
    session.add(row)
    await session.flush()
    log.info("seed_outbound_profile", name="xray-main")


async def run_check(session: AsyncSession, row: ProxyProfile) -> None:
    """Run an active check and persist status/latency (no secrets stored in result)."""
    prof = _build_profile(row)
    if prof is None:
        row.last_status = "failing"
        row.last_error_category = "build_failed"
        return
    result = await prof.check()
    row.last_checked_at = datetime.now(timezone.utc)
    row.last_status = "ok" if result.ok else "failing"
    row.last_latency_ms = result.latency_ms
    if not result.ok:
        row.error_count += 1
        row.last_error_category = result.error_category
    else:
        row.last_error_category = None
