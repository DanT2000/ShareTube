"""Signed, expiring download tokens using itsdangerous."""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import settings

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="sharetube-download")
_admin_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="sharetube-admin-session")


def make_download_token(link_token: str) -> str:
    return _serializer.dumps({"t": link_token})


def verify_download_token(signed: str, max_age_seconds: int) -> str | None:
    try:
        data = _serializer.loads(signed, max_age=max_age_seconds)
        return data.get("t")
    except (BadSignature, SignatureExpired):
        return None


def make_admin_session(admin_id: str) -> str:
    return _admin_serializer.dumps({"a": admin_id})


def verify_admin_session(signed: str) -> str | None:
    try:
        data = _admin_serializer.loads(signed, max_age=settings.ADMIN_SESSION_TTL_HOURS * 3600)
        return data.get("a")
    except (BadSignature, SignatureExpired):
        return None
