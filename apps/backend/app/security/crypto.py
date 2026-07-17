"""Symmetric encryption for secrets stored in the DB (cookies, proxy configs)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


def _fernet() -> Fernet:
    # Derive a stable 32-byte key from SECRET_KEY.
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
