"""SSRF protection and URL validation.

Blocks non-http(s) schemes, private/loopback/link-local/reserved IPs (v4+v6),
cloud metadata endpoints, and re-checks IPs after DNS resolution to defend
against DNS rebinding. Every redirect target must be re-validated by the caller.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from ..config import settings

ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata / known-dangerous hosts.
_METADATA_HOSTS = {
    "169.254.169.254",  # AWS/GCP/Azure IMDS
    "metadata.google.internal",
    "metadata",
    "100.100.100.200",  # Alibaba
}

# Executable / dangerous file extensions that must never be treated as media.
BLOCKED_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".cmd", ".com", ".msi", ".scr", ".dll", ".so",
    ".php", ".py", ".pl", ".rb", ".jar", ".apk", ".deb", ".rpm", ".ps1",
}


class UrlValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ValidatedUrl:
    original: str
    normalized: str
    scheme: str
    host: str
    resolved_ips: list[str]


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    # IPv4-mapped IPv6 -> unwrap and re-check
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or (isinstance(addr, ipaddress.IPv6Address) and addr.is_site_local)
    )


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlValidationError("dns_error", "Не удалось разрешить доменное имя.") from exc
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise UrlValidationError("dns_error", "Домен не имеет IP-адресов.")
    return ips


_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise UrlValidationError("empty", "Пустая ссылка.")
    if len(raw) > settings.MAX_URL_LENGTH:
        raise UrlValidationError("too_long", "Ссылка слишком длинная.")
    # Add scheme only if the string has no scheme at all (bare domain pasted).
    # Do NOT prepend for data:/file:/ftp: — keep their scheme so validation can reject them.
    if not _SCHEME_RE.match(raw):
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").strip()
        port = parts.port
    except ValueError as exc:
        raise UrlValidationError("bad_url", "Некорректная ссылка.") from exc
    if not host:
        raise UrlValidationError("no_host", "В ссылке отсутствует домен.")

    is_ipv6 = ":" in host  # urlsplit strips the [] brackets from IPv6 hostnames
    if is_ipv6:
        host_ascii = host
    else:
        # IDN normalization (punycode) — defends against homograph tricks.
        try:
            host_ascii = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            host_ascii = host

    netloc = f"[{host_ascii}]" if is_ipv6 else host_ascii
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def validate_url(raw: str, *, for_download: bool = False) -> ValidatedUrl:
    """Validate a user-supplied URL against SSRF rules.

    Raises UrlValidationError with a user-safe russian message on any violation.
    """
    normalized = normalize_url(raw)
    parts = urlsplit(normalized)
    scheme = parts.scheme.lower()

    if scheme not in ALLOWED_SCHEMES:
        raise UrlValidationError("scheme", "Разрешены только http и https ссылки.")

    host = (parts.hostname or "").lower()
    if not host:
        raise UrlValidationError("no_host", "В ссылке отсутствует домен.")

    if host in _METADATA_HOSTS:
        raise UrlValidationError("blocked_host", "Доступ к этому адресу запрещён.")

    # Domain allow/deny lists (match host or any parent domain).
    labels = host.split(".")
    candidates = {".".join(labels[i:]) for i in range(len(labels))}
    deny = settings.domain_denylist_set
    allow = settings.domain_allowlist_set
    if deny and (candidates & deny):
        raise UrlValidationError("denylist", "Этот домен заблокирован администратором.")
    if allow and not (candidates & allow):
        raise UrlValidationError("allowlist", "Этот домен не входит в список разрешённых.")

    # If host is a literal IP, block private ranges directly.
    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if _is_blocked_ip(host):
            raise UrlValidationError("private_ip", "Доступ к внутренним адресам запрещён.")
        resolved = [host]
    else:
        resolved = _resolve(host)
        # Re-check EVERY resolved IP (defends DNS rebinding).
        for ip in resolved:
            if _is_blocked_ip(ip):
                raise UrlValidationError("private_ip", "Домен указывает на внутренний адрес — запрещено.")

    return ValidatedUrl(
        original=raw.strip(),
        normalized=normalized,
        scheme=scheme,
        host=host,
        resolved_ips=resolved,
    )


def validate_redirect(target_url: str) -> ValidatedUrl:
    """Re-validate a redirect Location against the same SSRF rules."""
    return validate_url(target_url, for_download=True)
