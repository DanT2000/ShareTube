"""Delivery decision logic. Decision is based on ACTUAL size, never duration.

Limits come from config, not scattered constants.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from ..models import ContentType, DeliveryMethod


@dataclass
class DeliveryDecision:
    method: DeliveryMethod
    as_document: bool = False       # send video as document (no streaming) if not mp4/h264
    reason: str = ""
    offer_lower_quality: bool = False
    offer_audio_only: bool = False


def decide_video_delivery(size_bytes: int, *, vcodec: str | None, acodec: str | None,
                          ext: str | None, local_bot_enabled: bool | None = None) -> DeliveryDecision:
    """Route a finished video by its real size and codec compatibility."""
    local_enabled = settings.LOCAL_BOT_API_ENABLED if local_bot_enabled is None else local_bot_enabled

    streamable = (
        (ext or "").lower() in ("mp4", "m4v", "mov")
        and (vcodec or "").lower().startswith(("avc", "h264"))
        and (acodec or "").lower().startswith(("aac", "mp4a"))
    )

    if size_bytes <= settings.cloud_bot_safe_bytes:
        return DeliveryDecision(DeliveryMethod.CLOUD_BOT, as_document=not streamable,
                                reason="fits cloud bot limit")
    if local_enabled and size_bytes <= settings.local_bot_safe_bytes:
        return DeliveryDecision(DeliveryMethod.LOCAL_BOT, as_document=not streamable,
                                reason="fits local bot limit")
    # too big for any bot upload -> signed link + offers
    return DeliveryDecision(DeliveryMethod.SIGNED_LINK, reason="exceeds bot limits",
                            offer_lower_quality=True, offer_audio_only=True)


def decide_audio_delivery(size_bytes: int, *, local_bot_enabled: bool | None = None) -> DeliveryDecision:
    local_enabled = settings.LOCAL_BOT_API_ENABLED if local_bot_enabled is None else local_bot_enabled
    if size_bytes <= settings.cloud_bot_safe_bytes:
        return DeliveryDecision(DeliveryMethod.CLOUD_BOT, reason="fits cloud bot limit")
    if local_enabled and size_bytes <= settings.local_bot_safe_bytes:
        return DeliveryDecision(DeliveryMethod.LOCAL_BOT, reason="fits local bot limit")
    return DeliveryDecision(DeliveryMethod.SIGNED_LINK, reason="exceeds bot limits")


def decide_photo_group_delivery(total_bytes: int, item_count: int,
                                *, local_bot_enabled: bool | None = None) -> DeliveryDecision:
    """Photos: albums if small enough; else ZIP + signed link."""
    local_enabled = settings.LOCAL_BOT_API_ENABLED if local_bot_enabled is None else local_bot_enabled
    per_photo_limit = settings.cloud_bot_safe_bytes
    if total_bytes <= (settings.local_bot_safe_bytes if local_enabled else per_photo_limit * item_count):
        method = DeliveryMethod.LOCAL_BOT if (local_enabled and total_bytes > per_photo_limit) else DeliveryMethod.CLOUD_BOT
        return DeliveryDecision(method, reason="album delivery")
    return DeliveryDecision(DeliveryMethod.ZIP_LINK, reason="gallery too large -> zip link")


def chunk_album(items: list, max_per_group: int = 10) -> list[list]:
    """Split a media list into Telegram album groups of up to 10, preserving order."""
    return [items[i:i + max_per_group] for i in range(0, len(items), max_per_group)]
