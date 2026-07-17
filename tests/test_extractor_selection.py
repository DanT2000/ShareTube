"""Source detection & extractor chain selection tests."""
from app.extractors.selector import get_extractor_chain
from app.extractors.sources import detect_source, guess_content_type
from app.models import ContentType


def test_detect_sources():
    cases = {
        "https://www.youtube.com/watch?v=x": "youtube",
        "https://youtu.be/x": "youtube",
        "https://www.youtube.com/shorts/x": "youtube",
        "https://vk.com/video-1_2": "vk",
        "https://vkvideo.ru/video-1_2": "vk",
        "https://www.instagram.com/p/xxx/": "instagram",
        "https://www.tiktok.com/@u/video/1": "tiktok",
        "https://vimeo.com/12345": "vimeo",
        "https://clips.twitch.tv/xyz": "twitch",
        "https://x.com/u/status/1": "twitter",
        "https://twitter.com/u/status/1": "twitter",
        "https://cdn.example.com/movie.mp4": "direct",
        "https://example.org/some/page": "generic",
    }
    for url, expected in cases.items():
        assert detect_source(url) == expected, url


def test_content_type_hints():
    assert guess_content_type("youtube", "https://youtube.com/shorts/x") == ContentType.SHORT
    assert guess_content_type("tiktok", "https://tiktok.com/@u/video/1") == ContentType.SHORT
    assert guess_content_type("direct", "https://x/y.mp3") == ContentType.AUDIO
    assert guess_content_type("direct", "https://x/y.jpg") == ContentType.PHOTO


def test_chain_youtube_prefers_ytdlp():
    chain = get_extractor_chain("youtube", "https://youtube.com/watch?v=x")
    assert chain[0].name == "yt-dlp"
    assert chain[-1].name == "generic"


def test_chain_instagram_tries_gallery_first():
    chain = get_extractor_chain("instagram", "https://instagram.com/p/x/")
    names = [e.name for e in chain]
    assert names[0] == "gallery-dl"
    assert "yt-dlp" in names


def test_chain_direct_uses_directfile():
    chain = get_extractor_chain("direct", "https://cdn/x.mp4")
    assert chain[0].name == "direct-file"


def test_chain_has_fallback():
    for src in ("youtube", "vk", "instagram", "tiktok", "generic"):
        chain = get_extractor_chain(src, "https://x/y")
        assert len(chain) >= 2, src
