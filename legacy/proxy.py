
from __future__ import annotations

import argparse
import os
from typing import Dict, Optional, Tuple
from urllib.parse import quote

import requests

DEFAULT_TEST_URL = os.getenv("PROXY_TEST_URL", "https://api.ipify.org")  # plain text IP
DEFAULT_TIMEOUT = float(os.getenv("PROXY_TIMEOUT", "15"))


def build_proxy_url(host: str, port: int, user: Optional[str] = None, password: Optional[str] = None) -> str:
    """
    РЎРѕР±РёСЂР°РµС‚ URL РІРёРґР°:
        http://user:pass@host:port
    user/pass СЌРєСЂР°РЅРёСЂСѓСЋС‚СЃСЏ (РЅР° СЃР»СѓС‡Р°Р№ СЃРїРµС†СЃРёРјРІРѕР»РѕРІ).
    """
    if user:
        u = quote(user, safe="")
        p = quote(password or "", safe="")
        auth = f"{u}:{p}@"
    else:
        auth = ""
    return f"http://{auth}{host}:{port}"


def make_session(
    host: str,
    port: int,
    user: Optional[str] = None,
    password: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    headers: Optional[Dict[str, str]] = None,
) -> requests.Session:
    """
    РЎРѕР·РґР°С‘С‚ requests.Session СЃ HTTP-РїСЂРѕРєСЃРё (РїСЂРёРјРµРЅСЏРµС‚СЃСЏ Рё Рє HTTPS).
    """
    proxy_url = build_proxy_url(host, port, user, password)

    sess = requests.Session()
    sess.proxies.update({
        "http": proxy_url,
        "https": proxy_url,   # HTTPS С‚РѕР¶Рµ РїРѕР№РґС‘С‚ С‡РµСЂРµР· HTTP CONNECT РїСЂРѕРєСЃРё
    })
    # Р‘Р°Р·РѕРІС‹Рµ Р·Р°РіРѕР»РѕРІРєРё вЂ” РёРЅРѕРіРґР° РїРѕР»РµР·РЅРѕ РґР»СЏ РЅРµРєРѕС‚РѕСЂС‹С… РїСЂРѕРєСЃРё/CDN
    sess.headers.update({
        "User-Agent": headers.get("User-Agent") if headers and "User-Agent" in headers
        else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-requests",
        **({k: v for k, v in (headers or {}).items() if k.lower() != "user-agent"}),
    })
    # РЎРѕС…СЂР°РЅСЏРµРј С‚Р°Р№РјР°СѓС‚ РєР°Рє Р°С‚СЂРёР±СѓС‚ РґР»СЏ СѓРґРѕР±СЃС‚РІР°
    sess._default_timeout = timeout  # type: ignore[attr-defined]
    return sess


def get_ip(session: Optional[requests.Session] = None, test_url: str = DEFAULT_TEST_URL) -> str:
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ РІРЅРµС€РЅРёР№ IP РєР°Рє СЃС‚СЂРѕРєСѓ (Р±РµР· Р»РёС€РЅРµРіРѕ).
    Р•СЃР»Рё session=None вЂ” Р·Р°РїСЂРѕСЃ Р±РµР· РїСЂРѕРєСЃРё.
    """
    s = session or requests
    resp = s.get(test_url, timeout=getattr(s, "_default_timeout", DEFAULT_TIMEOUT))  # type: ignore[attr-defined]
    resp.raise_for_status()
    return resp.text.strip()


def check_proxy_ip(
    session: requests.Session,
    test_url: str = DEFAULT_TEST_URL,
) -> Tuple[bool, str, str]:
    """
    РЎСЂР°РІРЅРёРІР°РµС‚ IP Р±РµР· РїСЂРѕРєСЃРё Рё С‡РµСЂРµР· РїСЂРѕРєСЃРё.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ (ok, direct_ip, via_proxy_ip), РіРґРµ ok=True, РµСЃР»Рё IP РѕС‚Р»РёС‡Р°РµС‚СЃСЏ (Р·РЅР°С‡РёС‚, СЂРµР°Р»СЊРЅРѕ С‡РµСЂРµР· РїСЂРѕРєСЃРё).
    """
    direct_ip = get_ip(None, test_url=test_url)  # Р±РµР· РїСЂРѕРєСЃРё
    via_proxy_ip = get_ip(session, test_url=test_url)  # С‡РµСЂРµР· РїСЂРѕРєСЃРё
    return (direct_ip != via_proxy_ip, direct_ip, via_proxy_ip)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HTTP proxy helper + IP check")
    p.add_argument("--host", required=True, help="РџСЂРѕРєСЃРё С…РѕСЃС‚ (IP/РґРѕРјРµРЅ)")
    p.add_argument("--port", type=int, required=True, help="РџСЂРѕРєСЃРё РїРѕСЂС‚, РЅР°РїСЂ. 8080")
    p.add_argument("--user", help="Р›РѕРіРёРЅ РґР»СЏ РїСЂРѕРєСЃРё")
    p.add_argument("--password", help="РџР°СЂРѕР»СЊ РґР»СЏ РїСЂРѕРєСЃРё")
    p.add_argument("--test-url", default=DEFAULT_TEST_URL, help=f"URL РїСЂРѕРІРµСЂРєРё IP (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ {DEFAULT_TEST_URL})")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"РўР°Р№РјР°СѓС‚, СЃРµРє (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ {DEFAULT_TIMEOUT})")
    return p.parse_args()


def main() -> None:
    # Р’РџРРЁР РЎР®Р”Рђ РЎР’РћР Р”РђРќРќР«Р•
    HOST = "104.164.54.51"
    PORT = 59140
    USER = "ShareTube"
    PASS = "<REDACTED>"

    sess = make_session(host=HOST, port=PORT, user=USER, password=PASS)

    try:
        ok, direct_ip, via_proxy_ip = check_proxy_ip(sess)
        print(f"Direct IP : {direct_ip}")
        print(f"Proxy  IP : {via_proxy_ip}")
        print("вњ… Р§РµСЂРµР· РїСЂРѕРєСЃРё" if ok else "вљ пёЏ РќРµ С‡РµСЂРµР· РїСЂРѕРєСЃРё")
    except requests.RequestException as e:
        print(f"вќЊ РћС€РёР±РєР°: {e}")

if __name__ == "__main__":
    main()

