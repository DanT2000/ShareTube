"""Extractor selection and controlled fallback chain."""
from __future__ import annotations

from ..logging_config import get_logger
from .base import ExtractError, MediaExtractor, MediaMetadata
from .directfile import DirectFileExtractor
from .gallerydl import GalleryDlExtractor
from .generic import GenericExtractor
from .sources import detect_source
from .vk import VkExtractor
from .ytdlp import YtDlpExtractor

log = get_logger("selector")

# Instantiated once; extractors are stateless.
_YTDLP = YtDlpExtractor()
_GALLERY = GalleryDlExtractor()
_VK = VkExtractor()
_DIRECT = DirectFileExtractor()
_GENERIC = GenericExtractor()


def get_extractor_chain(source: str, url: str) -> list[MediaExtractor]:
    """Return an ordered list of extractors to try for this source.

    Primary handler first, then a controlled fallback chain.
    """
    if source == "direct":
        return [_DIRECT, _GENERIC]
    if source == "vk":
        return [_VK, _GALLERY, _GENERIC]
    if source == "instagram":
        # posts may be photo carousel (gallery-dl) or reel video (yt-dlp)
        return [_GALLERY, _YTDLP, _GENERIC]
    if source in {"youtube", "tiktok", "vimeo", "twitch", "twitter"}:
        return [_YTDLP, _GENERIC]
    return [_YTDLP, _GALLERY, _GENERIC]


async def analyze_url(url: str, *, proxy_url: str | None,
                      cookies_path: str | None = None) -> MediaMetadata:
    """Try the extractor chain until one produces metadata. Non-retriable errors
    from a primary extractor still allow trying the next; the last error is raised.
    """
    source = detect_source(url)
    chain = get_extractor_chain(source, url)
    last_error: ExtractError | None = None
    for extractor in chain:
        try:
            meta = await extractor.fetch_metadata(url, proxy_url=proxy_url, cookies_path=cookies_path)
            log.info("analyze_ok", source=source, extractor=extractor.name,
                     content_type=meta.content_type.value)
            return meta
        except ExtractError as exc:
            last_error = exc
            log.info("analyze_fallback", source=source, extractor=extractor.name, code=exc.code)
            # auth_required / removed are definitive — do not keep trying blindly
            if exc.code in {"auth_required", "removed", "too_large"}:
                raise
            continue
    raise last_error or ExtractError("unsupported", "Эта ссылка не поддерживается.")


def get_extractor_by_name(name: str) -> MediaExtractor:
    return {
        "yt-dlp": _YTDLP, "gallery-dl": _GALLERY, "vk": _VK,
        "direct-file": _DIRECT, "generic": _GENERIC,
    }.get(name, _GENERIC)
