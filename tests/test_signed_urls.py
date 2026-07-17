"""Signed download token tests."""
import time

from app.security import signed_urls


def test_roundtrip():
    tok = signed_urls.make_download_token("abc123")
    assert signed_urls.verify_download_token(tok, 60) == "abc123"


def test_expired():
    tok = signed_urls.make_download_token("abc123")
    time.sleep(2.1)
    assert signed_urls.verify_download_token(tok, 1) is None


def test_tampered():
    tok = signed_urls.make_download_token("abc123")
    assert signed_urls.verify_download_token(tok + "x", 60) is None


def test_admin_session_roundtrip():
    s = signed_urls.make_admin_session("5")
    assert signed_urls.verify_admin_session(s) == "5"
