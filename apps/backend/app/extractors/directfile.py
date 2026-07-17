"""Direct file extractor — downloads a file from a direct http(s) URL through the proxy.

Re-validates the URL (SSRF) and every redirect; enforces size limit while streaming.
"""
from __future__ import annotations

import os

import httpx

from ..logging_config import get_logger
from ..models import ContentType
from ..security.filenames import sanitize_filename
from ..security.ssrf import validate_url
from .base import (
    DownloadLimits,
    DownloadResult,
    ExtractError,
    Format,
    MediaExtractor,
    MediaMetadata,
    ProgressCallback,
)
from .sources import guess_content_type

log = get_logger("directfile")

_MIME_CT = {
    "video": ContentType.VIDEO, "audio": ContentType.AUDIO, "image": ContentType.PHOTO,
}


class DirectFileExtractor(MediaExtractor):
    name = "direct-file"

    def can_handle(self, source: str, url: str) -> bool:
        return source == "direct"

    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        validate_url(url, for_download=True)
        size = None
        mime = None
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=25, follow_redirects=False) as client:
                r = await self._head_follow(client, url)
                size = int(r.headers.get("content-length", 0)) or None
                mime = r.headers.get("content-type", "").split(";")[0] or None
        except httpx.HTTPError:
            pass  # some servers reject HEAD; metadata stays approximate
        ctype = guess_content_type("direct", url)
        if mime:
            ctype = _MIME_CT.get(mime.split("/")[0], ctype)
        filename = sanitize_filename(os.path.basename(url.split("?")[0]) or "file")
        fmt = Format(label="original", format_selector=None, ext=os.path.splitext(filename)[1].lstrip("."),
                     approx_size_bytes=size, size_is_estimate=size is None)
        return MediaMetadata(source="direct", extractor=self.name, content_type=ctype,
                             title=filename, formats=[fmt], raw={"mime": mime})

    async def _head_follow(self, client: httpx.AsyncClient, url: str, depth: int = 0):
        if depth > 5:
            raise ExtractError("too_many_redirects", "Слишком много перенаправлений.")
        r = await client.head(url)
        if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
            target = str(httpx.URL(r.url).join(r.headers["location"]))
            validate_url(target, for_download=True)  # re-check every redirect
            return await self._head_follow(client, target, depth + 1)
        return r

    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: DownloadLimits) -> DownloadResult:
        os.makedirs(work_dir, exist_ok=True)
        validate_url(url, for_download=True)
        filename = sanitize_filename(os.path.basename(url.split("?")[0]) or "file")
        dest = os.path.join(work_dir, filename)
        downloaded = 0
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=None, follow_redirects=False) as client:
                current = url
                for _ in range(6):
                    async with client.stream("GET", current) as resp:
                        if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                            current = str(httpx.URL(resp.url).join(resp.headers["location"]))
                            validate_url(current, for_download=True)
                            continue
                        resp.raise_for_status()
                        total = int(resp.headers.get("content-length", 0)) or None
                        with open(dest, "wb") as f:
                            async for chunk in resp.aiter_bytes(256 * 1024):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if downloaded > limits.max_bytes:
                                    raise ExtractError("too_large", "Превышен лимит размера файла.")
                                if progress:
                                    progress({"status": "downloading", "downloaded_bytes": downloaded,
                                              "total_bytes": total})
                        break
                else:
                    raise ExtractError("too_many_redirects", "Слишком много перенаправлений.")
        except httpx.HTTPError as exc:
            raise ExtractError("network", "Не удалось скачать файл. Источник недоступен.",
                               retriable=True) from exc
        ctype = guess_content_type("direct", url)
        return DownloadResult(files=[dest], primary_path=dest, content_type=ctype,
                              total_bytes=os.path.getsize(dest))
