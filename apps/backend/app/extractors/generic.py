"""Generic extractor — last resort, tries yt-dlp for arbitrary supported sites."""
from __future__ import annotations

from .base import DownloadLimits, DownloadResult, Format, MediaExtractor, MediaMetadata, ProgressCallback
from .ytdlp import YtDlpExtractor


class GenericExtractor(MediaExtractor):
    name = "generic"

    def __init__(self):
        self._ytdlp = YtDlpExtractor()

    def can_handle(self, source: str, url: str) -> bool:
        return True  # always the final fallback

    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        meta = await self._ytdlp.fetch_metadata(url, proxy_url=proxy_url, cookies_path=cookies_path)
        meta.extractor = self.name
        return meta

    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: DownloadLimits) -> DownloadResult:
        return await self._ytdlp.download(
            url, work_dir=work_dir, fmt=fmt, proxy_url=proxy_url,
            cookies_path=cookies_path, progress=progress, limits=limits)
