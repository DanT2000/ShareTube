"""Filename sanitization & path-traversal tests."""
import os

import pytest

from app.security.filenames import safe_join, sanitize_filename


def test_strips_directories():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/abs/path/video.mp4") == "video.mp4"
    assert sanitize_filename("a\\b\\c.mp4") == "c.mp4"


def test_neutralises_executables():
    assert sanitize_filename("evil.exe").endswith(".exe.bin")
    assert sanitize_filename("run.sh").endswith(".sh.bin")


def test_removes_control_and_traversal():
    out = sanitize_filename("na..me\x00.mp4")
    assert ".." not in out
    assert "\x00" not in out


def test_keeps_normal_names():
    assert sanitize_filename("My Video 1080p.mp4") == "My Video 1080p.mp4"


def test_empty_defaults():
    assert sanitize_filename("") == "file"
    assert sanitize_filename("...") == "file"


def test_safe_join_ok(tmp_path):
    p = safe_join(str(tmp_path), "a", "b.mp4")
    assert p.startswith(str(tmp_path))


def test_safe_join_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "..", "..", "etc", "passwd")
