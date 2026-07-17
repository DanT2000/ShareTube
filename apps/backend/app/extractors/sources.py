"""Source detection from a normalized URL host/path. No downloading here."""
from __future__ import annotations

from urllib.parse import urlsplit

from ..models import ContentType

# host suffix -> source name
_HOST_MAP = {
    "youtube.com": "youtube", "youtu.be": "youtube", "youtube-nocookie.com": "youtube",
    "vk.com": "vk", "vkvideo.ru": "vk", "vk.ru": "vk",
    "instagram.com": "instagram", "instagr.am": "instagram",
    "tiktok.com": "tiktok", "vt.tiktok.com": "tiktok",
    "vimeo.com": "vimeo",
    "twitch.tv": "twitch", "clips.twitch.tv": "twitch",
    "twitter.com": "twitter", "x.com": "twitter", "t.co": "twitter",
}

# sources primarily served by gallery-dl (photo galleries)
GALLERY_SOURCES = {"instagram"}
# sources served by yt-dlp video
YTDLP_SOURCES = {"youtube", "vk", "tiktok", "vimeo", "twitch", "twitter", "instagram"}

_DIRECT_FILE_EXT = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv",
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
}


def detect_source(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    for i in range(len(labels)):
        suffix = ".".join(labels[i:])
        if suffix in _HOST_MAP:
            return _HOST_MAP[suffix]
    # direct file?
    path = urlsplit(url).path.lower()
    for ext in _DIRECT_FILE_EXT:
        if path.endswith(ext):
            return "direct"
    return "generic"


def guess_content_type(source: str, url: str) -> ContentType:
    path = urlsplit(url).path.lower()
    if source == "youtube":
        if "/shorts/" in path:
            return ContentType.SHORT
        if "list=" in urlsplit(url).query or "/playlist" in path:
            return ContentType.PLAYLIST
        return ContentType.VIDEO
    if source == "instagram":
        if "/reel/" in path or "/reels/" in path:
            return ContentType.SHORT
        return ContentType.MIXED  # posts may be photo carousel or video; resolved on analyze
    if source == "tiktok":
        return ContentType.SHORT
    if source == "vk":
        if "/wall" in path or "wall" in path:
            return ContentType.MIXED
        return ContentType.VIDEO
    if source == "direct":
        for ext in (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"):
            if path.endswith(ext):
                return ContentType.AUDIO
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            if path.endswith(ext):
                return ContentType.PHOTO
        return ContentType.VIDEO
    return ContentType.UNKNOWN
