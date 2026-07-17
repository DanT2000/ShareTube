"""MediaExtractor interface and shared data structures."""
from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import ContentType

ProgressCallback = Callable[[dict], None]


class ExtractError(Exception):
    """Extractor failure with a stable error code and a user-safe russian message."""

    def __init__(self, code: str, message: str, *, retriable: bool = False):
        self.code = code
        self.message = message
        self.retriable = retriable
        super().__init__(message)


@dataclass
class Format:
    label: str                      # "1080p", "720p", "audio", "original", "auto"
    format_selector: str | None     # yt-dlp -f value (built server-side only)
    ext: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    approx_size_bytes: int | None = None
    size_is_estimate: bool = True
    audio_only: bool = False


@dataclass
class MediaItemMeta:
    position: int
    kind: str                       # photo | video | audio
    url: str | None = None
    filename: str | None = None
    width: int | None = None
    height: int | None = None
    duration_sec: int | None = None


@dataclass
class MediaMetadata:
    source: str
    extractor: str
    content_type: ContentType
    title: str | None = None
    author: str | None = None
    duration_sec: int | None = None
    thumbnail_url: str | None = None
    item_count: int = 1
    is_live: bool = False
    formats: list[Format] = field(default_factory=list)
    items: list[MediaItemMeta] = field(default_factory=list)
    raw: dict | None = None


@dataclass
class DownloadResult:
    files: list[str]                # absolute paths, in order
    primary_path: str | None
    content_type: ContentType
    total_bytes: int


class MediaExtractor(abc.ABC):
    """Extensible extractor interface. Business logic never binds to a library directly."""

    name: str = "base"

    @abc.abstractmethod
    def can_handle(self, source: str, url: str) -> bool:
        ...

    @abc.abstractmethod
    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        """Probe metadata WITHOUT downloading the full media."""
        ...

    @abc.abstractmethod
    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: "DownloadLimits") -> DownloadResult:
        ...


@dataclass
class DownloadLimits:
    max_bytes: int
    max_duration_sec: int | None
    max_items: int
    timeout_sec: int
    rate_limit_kbps: int = 0
