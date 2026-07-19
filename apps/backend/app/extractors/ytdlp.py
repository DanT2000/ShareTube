"""yt-dlp extractor for video/audio sources. Uses subprocess with array args only."""
from __future__ import annotations

import json
import os
import shutil

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
from .sources import YTDLP_SOURCES, detect_source, guess_content_type

log = get_logger("ytdlp")
YTDLP_BIN = os.getenv("YTDLP_BIN", "yt-dlp")


def _pot_args() -> list[str]:
    """Extractor args to use the bgutil PO-token provider (bypasses YouTube bot-check)."""
    from ..config import settings
    if not settings.POT_PROVIDER_URL:
        return []
    return ["--extractor-args", f"youtubepot-bgutilhttp:base_url={settings.POT_PROVIDER_URL}"]

# Height presets -> yt-dlp format selector. Prefer ready H.264/AAC MP4 (no transcode).
_HEIGHT_SELECTOR = (
    "bv*[height<={h}][ext=mp4][vcodec^=avc]+ba[ext=m4a]/"
    "bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
    "b[height<={h}][ext=mp4]/bv*[height<={h}]+ba/b[height<={h}]/best"
)


class YtDlpExtractor(MediaExtractor):
    name = "yt-dlp"

    def can_handle(self, source: str, url: str) -> bool:
        return source in YTDLP_SOURCES or source == "generic"

    async def fetch_metadata(self, url: str, *, proxy_url: str | None,
                             cookies_path: str | None = None) -> MediaMetadata:
        argv = [YTDLP_BIN, "-J", "--no-warnings", "--no-playlist",
                "--socket-timeout", "30", "--no-download", *_pot_args()]
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
            info = json.loads(res.stdout.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise ExtractError("parse_error", "Не удалось разобрать данные источника.") from exc
        return self._build_metadata(url, info)

    def _build_metadata(self, url: str, info: dict) -> MediaMetadata:
        source = detect_source(url)
        is_live = bool(info.get("is_live") or info.get("live_status") == "is_live")
        duration = info.get("duration")
        ctype = guess_content_type(source, url)
        if is_live:
            ctype = ContentType.LIVE
        elif duration and duration <= 60 and source in {"youtube", "instagram", "tiktok"}:
            ctype = ContentType.SHORT if ctype in (ContentType.VIDEO, ContentType.MIXED) else ctype
        elif ctype == ContentType.MIXED:
            ctype = ContentType.VIDEO

        formats = self._build_formats(info)
        thumb = info.get("thumbnail")
        if not thumb and info.get("thumbnails"):
            thumb = info["thumbnails"][-1].get("url")

        return MediaMetadata(
            source=source, extractor=self.name, content_type=ctype,
            title=info.get("title"), author=info.get("uploader") or info.get("channel"),
            duration_sec=int(duration) if duration else None, thumbnail_url=thumb,
            item_count=1, is_live=is_live, formats=formats,
            raw={"id": info.get("id"), "webpage_url": info.get("webpage_url")},
        )

    def _build_formats(self, info: dict) -> list[Format]:
        raw_formats = info.get("formats") or []
        heights = sorted({f.get("height") for f in raw_formats if f.get("height")})
        duration = info.get("duration") or 0

        def size_for_height(h: int) -> tuple[int | None, bool]:
            cands = [f for f in raw_formats if f.get("height") == h]
            best = None
            for f in cands:
                s = f.get("filesize") or f.get("filesize_approx")
                if s:
                    best = s if best is None else max(best, s)
            if best:
                # add approximate audio track (~128kbps) if video-only
                return int(best) + int(duration * 128 * 1024 / 8), False
            tbr = max((f.get("tbr") or 0) for f in cands) if cands else 0
            if tbr and duration:
                return int(tbr * 1000 / 8 * duration), True
            return None, True

        formats: list[Format] = []
        formats.append(Format(label="auto", format_selector=_HEIGHT_SELECTOR.format(h=1080),
                              ext="mp4", size_is_estimate=True))
        for target in (1080, 720, 480):
            if any((h or 0) >= target - 120 for h in heights) or not heights:
                sz, est = size_for_height(target)
                formats.append(Format(label=f"{target}p",
                                      format_selector=_HEIGHT_SELECTOR.format(h=target),
                                      ext="mp4", height=target, approx_size_bytes=sz,
                                      size_is_estimate=est))
        # minimal size
        formats.append(Format(label="min", format_selector="worst[ext=mp4]/worst",
                              ext="mp4", size_is_estimate=True))
        # original / best
        best_sz = None
        for f in raw_formats:
            s = f.get("filesize") or f.get("filesize_approx")
            if s and (best_sz is None or s > best_sz):
                best_sz = s
        formats.append(Format(label="original", format_selector="bv*+ba/best",
                              ext=None, approx_size_bytes=int(best_sz) if best_sz else None,
                              size_is_estimate=best_sz is None))
        # audio only
        a_sz = int(duration * 128 * 1024 / 8) if duration else None
        formats.append(Format(label="audio", format_selector="ba[ext=m4a]/ba/bestaudio",
                              ext="m4a", acodec="aac", audio_only=True,
                              approx_size_bytes=a_sz, size_is_estimate=True))
        return formats

    async def download(self, url: str, *, work_dir: str, fmt: Format, proxy_url: str | None,
                       cookies_path: str | None, progress: ProgressCallback | None,
                       limits: DownloadLimits) -> DownloadResult:
        os.makedirs(work_dir, exist_ok=True)
        out_tmpl = os.path.join(work_dir, "%(title).150B.%(ext)s")
        argv = [
            YTDLP_BIN, "--no-warnings", "--no-playlist", "--no-part",
            "--socket-timeout", "30", "--retries", "5", "--fragment-retries", "10",
            "-o", out_tmpl,
            "--max-filesize", str(limits.max_bytes),
            "--newline",
            "--progress-template",
            "download:PROGRESS %(progress.downloaded_bytes)s %(progress.total_bytes)s "
            "%(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s",
            *_pot_args(),
        ]
        if fmt.audio_only:
            argv += ["-f", fmt.format_selector or "ba/bestaudio",
                     "-x", "--audio-format", "m4a", "--audio-quality", "0"]
        else:
            argv += ["-f", fmt.format_selector or "bv*+ba/best",
                     "--merge-output-format", "mp4"]
        if limits.rate_limit_kbps:
            argv += ["--limit-rate", f"{limits.rate_limit_kbps}K"]
        if proxy_url:
            argv += ["--proxy", proxy_url]
        if cookies_path:
            argv += ["--cookies", cookies_path]
        argv.append(url)

        def on_line(line: str):
            if line.startswith("PROGRESS ") and progress:
                parts = line.split()
                def _f(x):
                    return None if x in ("NA", "None", "") else float(x)
                downloaded = _f(parts[1]) if len(parts) > 1 else None
                total = _f(parts[2]) if len(parts) > 2 else None
                total_est = _f(parts[3]) if len(parts) > 3 else None
                speed = _f(parts[4]) if len(parts) > 4 else None
                eta = _f(parts[5]) if len(parts) > 5 else None
                progress({
                    "status": "downloading",
                    "downloaded_bytes": downloaded,
                    "total_bytes": total or total_est,
                    "speed": speed, "eta": eta,
                })

        res = await sp.run(argv, timeout=limits.timeout_sec, cwd=work_dir, line_callback=on_line)
        if res.timed_out:
            raise ExtractError("timeout", "Превышено время ожидания загрузки.", retriable=True)
        if res.returncode != 0:
            raise self._classify(res.stderr.decode("utf-8", "replace"))

        files = [os.path.join(work_dir, f) for f in os.listdir(work_dir)
                 if os.path.isfile(os.path.join(work_dir, f))]
        if not files:
            raise ExtractError("no_output", "Не удалось получить файл.")
        primary = max(files, key=os.path.getsize)
        total = sum(os.path.getsize(f) for f in files)
        ctype = ContentType.AUDIO if fmt.audio_only else guess_content_type(detect_source(url), url)
        return DownloadResult(files=[primary], primary_path=primary, content_type=ctype,
                              total_bytes=total)

    def _classify(self, stderr: str) -> ExtractError:
        s = stderr.lower()
        if "requested format is not available" in s or "no video formats found" in s or \
                "no formats" in s:
            return ExtractError(
                "no_formats",
                "Источник не отдал форматы для этого видео (возможно, ограничение YouTube "
                "или требуется другой доступ). Попробуйте другое видео.")
        if "unsupported url" in s or "no video" in s:
            return ExtractError("unsupported", "Эта ссылка не поддерживается.")
        if "private" in s or "login required" in s or "sign in" in s or "authentication" in s:
            return ExtractError("auth_required", "Для этого контента требуется авторизация.")
        if "video unavailable" in s or "removed" in s or "not available" in s or "410" in s or "404" in s:
            return ExtractError("removed", "Публикация недоступна или удалена.")
        if "max-filesize" in s or "file is larger" in s:
            return ExtractError("too_large", "Превышен лимит размера файла.")
        if "timed out" in s or "timeout" in s or "connection" in s or "proxy" in s:
            return ExtractError("network", "Источник временно недоступен. Попробуйте позже.", retriable=True)
        if "http error 429" in s or "too many requests" in s:
            return ExtractError("rate_limited", "Источник ограничил частоту запросов. Попробуйте позже.", retriable=True)
        return ExtractError("extract_failed", "Не удалось получить формат. Возможно, источник изменил API.")


def ffprobe_info(path: str) -> dict:
    """Return {duration, has_audio, has_video, width, height} via ffprobe (best-effort)."""
    ffprobe = os.getenv("FFPROBE_BIN", "ffprobe")
    if not shutil.which(ffprobe):
        return {}
    import subprocess
    try:
        out = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format",
             "-show_streams", path],
            capture_output=True, timeout=30, check=False,
        )
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "duration": float(fmt.get("duration", 0)) if fmt.get("duration") else None,
        "has_audio": a is not None,
        "has_video": v is not None,
        "width": v.get("width") if v else None,
        "height": v.get("height") if v else None,
        "vcodec": v.get("codec_name") if v else None,
        "acodec": a.get("codec_name") if a else None,
    }
