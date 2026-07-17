"""Delivery size-routing tests. Decision is by actual size, never duration."""
from app.models import DeliveryMethod
from app.services.delivery import (
    chunk_album,
    decide_audio_delivery,
    decide_photo_group_delivery,
    decide_video_delivery,
)

MB = 1024 * 1024


def test_small_streamable_video_goes_cloud():
    d = decide_video_delivery(10 * MB, vcodec="avc1", acodec="mp4a", ext="mp4")
    assert d.method == DeliveryMethod.CLOUD_BOT
    assert d.as_document is False


def test_small_incompatible_video_sent_as_document():
    d = decide_video_delivery(10 * MB, vcodec="vp9", acodec="opus", ext="webm")
    assert d.method == DeliveryMethod.CLOUD_BOT
    assert d.as_document is True


def test_medium_video_uses_local_bot_when_enabled():
    d = decide_video_delivery(500 * MB, vcodec="avc1", acodec="mp4a", ext="mp4",
                              local_bot_enabled=True)
    assert d.method == DeliveryMethod.LOCAL_BOT


def test_medium_video_without_local_bot_gets_link():
    d = decide_video_delivery(500 * MB, vcodec="avc1", acodec="mp4a", ext="mp4",
                              local_bot_enabled=False)
    assert d.method == DeliveryMethod.SIGNED_LINK
    assert d.offer_lower_quality and d.offer_audio_only


def test_huge_video_always_link():
    d = decide_video_delivery(5000 * MB, vcodec="avc1", acodec="mp4a", ext="mp4",
                              local_bot_enabled=True)
    assert d.method == DeliveryMethod.SIGNED_LINK


def test_audio_routing():
    assert decide_audio_delivery(5 * MB).method == DeliveryMethod.CLOUD_BOT
    assert decide_audio_delivery(5000 * MB, local_bot_enabled=False).method == DeliveryMethod.SIGNED_LINK


def test_photo_group_small_album():
    d = decide_photo_group_delivery(5 * MB, 3)
    assert d.method in (DeliveryMethod.CLOUD_BOT, DeliveryMethod.LOCAL_BOT)


def test_photo_group_large_zip():
    d = decide_photo_group_delivery(9000 * MB, 40, local_bot_enabled=False)
    assert d.method == DeliveryMethod.ZIP_LINK


def test_chunk_album_preserves_order_and_size():
    items = list(range(23))
    groups = chunk_album(items, 10)
    assert [len(g) for g in groups] == [10, 10, 3]
    assert [x for g in groups for x in g] == items
