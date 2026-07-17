"""Telegram Mini App initData & Login Widget validation tests."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.security.telegram_auth import (
    InitDataError,
    validate_init_data,
    validate_login_widget,
)

BOT_TOKEN = "123456789:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz012"


def _make_init_data(user: dict, auth_date: int | None = None) -> str:
    auth_date = auth_date or int(time.time())
    fields = {"auth_date": str(auth_date), "query_id": "AAA",
              "user": json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = h
    return urlencode(fields)


def test_valid_init_data():
    init = _make_init_data({"id": 42, "first_name": "Tester"})
    data = validate_init_data(init, bot_token=BOT_TOKEN)
    assert data["user"]["id"] == 42


def test_tampered_hash_rejected():
    init = _make_init_data({"id": 42})
    tampered = init.replace("id%22%3A42", "id%22%3A999")
    with pytest.raises(InitDataError):
        validate_init_data(tampered, bot_token=BOT_TOKEN)


def test_missing_hash_rejected():
    with pytest.raises(InitDataError):
        validate_init_data("auth_date=123&user=%7B%7D", bot_token=BOT_TOKEN)


def test_expired_init_data_rejected():
    init = _make_init_data({"id": 1}, auth_date=int(time.time()) - 100000)
    with pytest.raises(InitDataError):
        validate_init_data(init, bot_token=BOT_TOKEN, max_age=3600)


def test_login_widget_valid():
    data = {"id": 7, "first_name": "A", "auth_date": int(time.time())}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    out = validate_login_widget(data, bot_token=BOT_TOKEN)
    assert out["id"] == 7


def test_login_widget_bad_hash():
    data = {"id": 7, "auth_date": int(time.time()), "hash": "deadbeef"}
    with pytest.raises(InitDataError):
        validate_login_widget(data, bot_token=BOT_TOKEN)
