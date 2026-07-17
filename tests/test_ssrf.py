"""URL validation & SSRF protection tests."""
import pytest

from app.security.ssrf import UrlValidationError, normalize_url, validate_url


def test_normalize_adds_scheme():
    assert normalize_url("youtube.com/watch?v=x").startswith("https://")


def test_rejects_non_http_schemes():
    for url in ("file:///etc/passwd", "ftp://host/file", "gopher://x", "data:text/plain,hi"):
        with pytest.raises(UrlValidationError):
            validate_url(url)


def test_blocks_localhost_and_loopback():
    for url in ("http://127.0.0.1/", "http://localhost/", "http://127.0.0.1:8989/admin",
                "http://[::1]/"):
        with pytest.raises(UrlValidationError) as e:
            validate_url(url)
        assert e.value.code in ("private_ip", "blocked_host")


def test_blocks_private_ipv4():
    for url in ("http://10.0.0.5/", "http://192.168.2.15/", "http://172.16.0.1/",
                "http://169.254.169.254/latest/meta-data/"):
        with pytest.raises(UrlValidationError):
            validate_url(url)


def test_blocks_cloud_metadata_host():
    with pytest.raises(UrlValidationError):
        validate_url("http://metadata.google.internal/computeMetadata/v1/")


def test_blocks_ipv4_mapped_ipv6_private():
    with pytest.raises(UrlValidationError):
        validate_url("http://[::ffff:10.0.0.1]/")


def test_allows_public_domain():
    v = validate_url("https://www.youtube.com/watch?v=abc")
    assert v.host == "www.youtube.com"
    assert v.scheme == "https"


def test_url_too_long():
    with pytest.raises(UrlValidationError) as e:
        validate_url("https://example.com/" + "a" * 5000)
    assert e.value.code == "too_long"


def test_denylist(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "DOMAIN_DENYLIST", "evil.com")
    with pytest.raises(UrlValidationError) as e:
        validate_url("https://sub.evil.com/x")
    assert e.value.code == "denylist"
