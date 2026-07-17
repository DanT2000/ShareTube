"""Telegram delivery helper used by the worker.

Sends video/audio/photo/album/document via cloud or Local Bot API, caches file_id,
and never attempts to hand a large file to Telegram via a plain HTTP URL.
"""
from __future__ import annotations

import os

import httpx

from ..config import settings
from ..logging_config import get_logger

log = get_logger("tg_delivery")


def _api_base() -> str:
    if settings.LOCAL_BOT_API_ENABLED:
        return f"{settings.LOCAL_BOT_API_BASE}/bot{settings.BOT_TOKEN}"
    return f"{settings.TELEGRAM_API_BASE}/bot{settings.BOT_TOKEN}"


def _use_local_path() -> bool:
    """With Local Bot API + shared volume, files are read by path (no re-upload)."""
    return settings.LOCAL_BOT_API_ENABLED


async def send_message(chat_id: int, text: str, **kw) -> dict:
    async with httpx.AsyncClient(timeout=30, proxy=settings.telegram_proxy) as client:
        r = await client.post(f"{_api_base()}/sendMessage",
                              json={"chat_id": chat_id, "text": text, **kw})
        return r.json()


async def edit_message(chat_id: int, message_id: int, text: str, **kw) -> dict:
    async with httpx.AsyncClient(timeout=30, proxy=settings.telegram_proxy) as client:
        r = await client.post(f"{_api_base()}/editMessageText",
                              json={"chat_id": chat_id, "message_id": message_id,
                                    "text": text, **kw})
        return r.json()


async def _send_file(method: str, chat_id: int, field: str, path: str, *,
                     caption: str | None = None, extra: dict | None = None,
                     cached_file_id: str | None = None) -> dict:
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    if extra:
        data.update({k: str(v) for k, v in extra.items()})

    timeout = httpx.Timeout(600.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, proxy=settings.telegram_proxy) as client:
        if cached_file_id:
            data[field] = cached_file_id
            r = await client.post(f"{_api_base()}/{method}", data=data)
            return r.json()
        if _use_local_path():
            # Local Bot API in --local mode accepts an absolute path reference.
            data[field] = f"file://{os.path.abspath(path)}"
            r = await client.post(f"{_api_base()}/{method}", data=data)
            js = r.json()
            if js.get("ok"):
                return js
            # fall through to multipart if path reference rejected
        with open(path, "rb") as fh:
            files = {field: (os.path.basename(path), fh)}
            r = await client.post(f"{_api_base()}/{method}", data=data, files=files)
            return r.json()


async def send_video(chat_id: int, path: str, *, caption=None, streamable=True,
                     width=None, height=None, duration=None, cached_file_id=None) -> dict:
    if not streamable:
        return await send_document(chat_id, path, caption=caption, cached_file_id=cached_file_id)
    extra = {"supports_streaming": "true"}
    if width:
        extra["width"] = width
    if height:
        extra["height"] = height
    if duration:
        extra["duration"] = duration
    return await _send_file("sendVideo", chat_id, "video", path, caption=caption,
                            extra=extra, cached_file_id=cached_file_id)


async def send_audio(chat_id: int, path: str, *, caption=None, cached_file_id=None) -> dict:
    return await _send_file("sendAudio", chat_id, "audio", path, caption=caption,
                            cached_file_id=cached_file_id)


async def send_photo(chat_id: int, path: str, *, caption=None, cached_file_id=None) -> dict:
    return await _send_file("sendPhoto", chat_id, "photo", path, caption=caption,
                            cached_file_id=cached_file_id)


async def send_document(chat_id: int, path: str, *, caption=None, cached_file_id=None) -> dict:
    return await _send_file("sendDocument", chat_id, "document", path, caption=caption,
                            cached_file_id=cached_file_id)


async def send_media_group(chat_id: int, paths: list[str], *, caption: str | None = None) -> dict:
    """Send 2..10 items as an album. Uses multipart with attach:// references."""
    media = []
    files = {}
    for i, path in enumerate(paths[:10]):
        is_video = path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
        key = f"file{i}"
        item = {"type": "video" if is_video else "photo", "media": f"attach://{key}"}
        if i == 0 and caption:
            item["caption"] = caption[:1024]
        media.append(item)
        files[key] = (os.path.basename(path), open(path, "rb"))
    import json as _json
    try:
        timeout = httpx.Timeout(600.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, proxy=settings.telegram_proxy) as client:
            r = await client.post(f"{_api_base()}/sendMediaGroup",
                                  data={"chat_id": str(chat_id), "media": _json.dumps(media)},
                                  files=files)
            return r.json()
    finally:
        for _, (_, fh) in files.items():
            fh.close()


def extract_file_id(response: dict, kind: str) -> str | None:
    """Pull the reusable file_id from a Bot API response."""
    if not response.get("ok"):
        return None
    result = response["result"]
    if isinstance(result, list):
        result = result[0] if result else {}
    for field in ("video", "audio", "document"):
        if field in result:
            return result[field].get("file_id")
    if "photo" in result and result["photo"]:
        return result["photo"][-1].get("file_id")
    return None
