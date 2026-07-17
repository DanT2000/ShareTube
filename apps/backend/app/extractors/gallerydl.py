"""gallery-dl extractor for photos, carousels and mixed galleries."""
from __future__ import annotations

import json
import os

from ..logging_config import get_logger
from ..models import ContentType
from . import subprocess_util as sp
from .base import (
    DownloadLimits,
    DownloadResult,
    ExtractError,
    Format,
    MediaExtractor,
    MediaItemMeta,
    MediaMetadata,
    ProgressCallback,
)
from .sources import GALLERY_SOURCES, detect_source

log = get_logger("gallery-dl")
GALLERYDL_BIN = os.getenv("GALLERYDL_BIN", "gallery-dl")


class GalleryDlExtractor(MediaExtractor):
    name = "gallery-dl"

    def can_handle(self, source: str, url: str) -> bool:
        return source in GALLERY_SOURCES

    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        argv = [GALLERYDL_BIN, "-j", "--no-download"]
        if proxy_url:
            argv += ["--proxy", proxy_url]
        if cookies_path:
            argv += ["--cookies", cookies_path]
        argv.append(url)

        res = await sp.run(argv, timeout=90)
        if res.timed_out:
            raise ExtractError("timeout", "Превышено время ожидания при анализе ссылки.", retriable=True)
        if res.returncode != 0:
            raise self._classify(res.stderr.decode("utf-8", "replace"))
        try:
            data = json.loads(res.stdout.decode("utf-8", "replace") or "[]")
        except json.JSONDecodeError as exc:
            raise ExtractError("parse_error", "Не удалось разобрать данные галереи.") from exc

        items: list[MediaItemMeta] = []
        title = None
        author = None
        pos = 0
        has_video = False
        for entry in data:
            # gallery-dl -j entries: [type, url, meta] or [type, meta]
            if not isinstance(entry, list):
                continue
            if len(entry) >= 3 and isinstance(entry[2], dict):
                meta = entry[2]
                media_url = entry[1] if isinstance(entry[1], str) else None
                ext = (meta.get("extension") or "").lower()
                kind = "video" if ext in ("mp4", "mov", "webm", "mkv") else "photo"
                has_video = has_video or kind == "video"
                title = title or meta.get("description") or meta.get("title")
                author = author or meta.get("username") or meta.get("uploader") or meta.get("author")
                items.append(MediaItemMeta(position=pos, kind=kind, url=media_url,
                                           filename=meta.get("filename"),
                                           width=meta.get("width"), height=meta.get("height")))
                pos += 1

        if not items:
            raise ExtractError("no_media", "В публикации не найдено медиа.")

        if len(items) == 1:
            ctype = ContentType.VIDEO if items[0].kind == "video" else ContentType.PHOTO
        elif has_video and any(i.kind == "photo" for i in items):
            ctype = ContentType.MIXED
        elif has_video:
            ctype = ContentType.VIDEO
        else:
            ctype = ContentType.PHOTO_CAROUSEL

        formats = [Format(label="original", format_selector=None, size_is_estimate=True)]
        return MediaMetadata(
            source=detect_source(url), extractor=self.name, content_type=ctype,
            title=(title or "")[:300] or None, author=author, item_count=len(items),
            formats=formats, items=items, thumbnail_url=items[0].url,
        )

    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: DownloadLimits) -> DownloadResult:
        os.makedirs(work_dir, exist_ok=True)
        argv = [
            GALLERYDL_BIN, "-D", work_dir,
            "--range", f"1-{limits.max_items}",
            "-o", "output.mode=null",
        ]
        if limits.rate_limit_kbps:
            argv += ["--limit-rate", f"{limits.rate_limit_kbps}k"]
        if proxy_url:
            argv += ["--proxy", proxy_url]
        if cookies_path:
            argv += ["--cookies", cookies_path]
        argv.append(url)

        if progress:
            progress({"status": "downloading", "downloaded_bytes": None, "total_bytes": None})

        res = await sp.run(argv, timeout=limits.timeout_sec, cwd=work_dir)
        if res.timed_out:
            raise ExtractError("timeout", "Превышено время ожидания загрузки.", retriable=True)
        if res.returncode != 0:
            raise self._classify(res.stderr.decode("utf-8", "replace"))

        files = sorted(
            os.path.join(work_dir, f) for f in os.listdir(work_dir)
            if os.path.isfile(os.path.join(work_dir, f))
        )
        if not files:
            raise ExtractError("no_output", "Не удалось получить файлы галереи.")
        total = sum(os.path.getsize(f) for f in files)
        if total > limits.max_bytes:
            raise ExtractError("too_large", "Превышен лимит размера публикации.")
        photos = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))]
        videos = [f for f in files if f.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))]
        if videos and photos:
            ctype = ContentType.MIXED
        elif videos:
            ctype = ContentType.VIDEO
        elif len(photos) == 1:
            ctype = ContentType.PHOTO
        else:
            ctype = ContentType.PHOTO_CAROUSEL
        return DownloadResult(files=files, primary_path=files[0], content_type=ctype,
                              total_bytes=total)

    def _classify(self, stderr: str) -> ExtractError:
        s = stderr.lower()
        if "login" in s or "authorization" in s or "private" in s or "age" in s:
            return ExtractError("auth_required", "Для этого контента требуется авторизация.")
        if "not found" in s or "404" in s or "deleted" in s:
            return ExtractError("removed", "Публикация недоступна или удалена.")
        if "unsupported" in s or "no extractor" in s:
            return ExtractError("unsupported", "Эта ссылка не поддерживается.")
        if "timeout" in s or "connection" in s or "proxy" in s:
            return ExtractError("network", "Источник временно недоступен. Попробуйте позже.", retriable=True)
        return ExtractError("extract_failed", "Не удалось получить галерею. Возможно, источник изменил API.")
