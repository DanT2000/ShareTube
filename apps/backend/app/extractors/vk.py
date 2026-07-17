"""VK extractor — routes VK video to yt-dlp and VK wall posts to gallery-dl."""
from __future__ import annotations

from urllib.parse import urlsplit

from .base import DownloadLimits, DownloadResult, Format, MediaExtractor, MediaMetadata, ProgressCallback
from .gallerydl import GalleryDlExtractor
from .ytdlp import YtDlpExtractor


class VkExtractor(MediaExtractor):
    name = "vk"

    def __init__(self):
        self._video = YtDlpExtractor()
        self._gallery = GalleryDlExtractor()

    def can_handle(self, source: str, url: str) -> bool:
        return source == "vk"

    def _is_wall(self, url: str) -> bool:
        path = urlsplit(url).path.lower()
        return "wall" in path or "wall" in urlsplit(url).query.lower()

    def _delegate(self, url: str) -> MediaExtractor:
        # wall posts may contain photos -> gallery-dl; pure video links -> yt-dlp
        return self._gallery if self._is_wall(url) else self._video

    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        meta = await self._delegate(url).fetch_metadata(url, proxy_url=proxy_url, cookies_path=cookies_path)
        meta.source = "vk"
        return meta

    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: DownloadLimits) -> DownloadResult:
        return await self._delegate(url).download(
            url, work_dir=work_dir, fmt=fmt, proxy_url=proxy_url,
            cookies_path=cookies_path, progress=progress, limits=limits)
