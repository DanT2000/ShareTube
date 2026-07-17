"""Telegram Mini App initData validation and Login Widget verification.

Never trust a user id sent by the frontend — always verify the HMAC here.
Per Telegram docs: secret_key = HMAC-SHA256("WebAppData", bot_token); the check
hash = HMAC-SHA256(secret_key, data_check_string).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from ..config import settings

MAX_AUTH_AGE_SECONDS = 24 * 3600


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, *, bot_token: str | None = None,
                       max_age: int = MAX_AUTH_AGE_SECONDS) -> dict:
    """Validate raw initData query string. Returns parsed dict incl. `user`.

    Raises InitDataError on any failure.
    """
    token = bot_token or settings.BOT_TOKEN
    if not token:
        raise InitDataError("bot token not configured")
    if not init_data:
        raise InitDataError("empty initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc, received_hash):
        raise InitDataError("hash mismatch")

    auth_date = int(pairs.get("auth_date", "0") or "0")
    if max_age and auth_date and (time.time() - auth_date > max_age):
        raise InitDataError("initData expired")

    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError as exc:
            raise InitDataError("bad user json") from exc
    return pairs


def validate_login_widget(data: dict, *, bot_token: str | None = None,
                          max_age: int = MAX_AUTH_AGE_SECONDS) -> dict:
    """Validate Telegram Login Widget payload (secret_key = SHA256(bot_token))."""
    token = bot_token or settings.BOT_TOKEN
    if not token:
        raise InitDataError("bot token not configured")
    data = dict(data)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data) if data[k] is not None)
    secret = hashlib.sha256(token.encode()).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise InitDataError("hash mismatch")
    auth_date = int(data.get("auth_date", 0) or 0)
    if max_age and auth_date and (time.time() - auth_date > max_age):
        raise InitDataError("expired")
    return data
