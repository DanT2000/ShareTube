"""FastAPI dependencies: user resolution and admin auth."""
from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import TelegramAccount, User
from .security.ratelimit import check_rate_limit
from .security.signed_urls import make_admin_session, verify_admin_session
from .security.telegram_auth import InitDataError, validate_init_data

SESSION_COOKIE = "st_session"
ADMIN_COOKIE = "st_admin"


async def _get_or_create_user_by_telegram(session: AsyncSession, tg: dict) -> User:
    tid = int(tg["id"])
    acc = (await session.execute(
        select(TelegramAccount).where(TelegramAccount.telegram_id == tid)
    )).scalar_one_or_none()
    if acc:
        user = await session.get(User, acc.user_id)
        if user:
            return user
    user = User(display_name=tg.get("first_name") or tg.get("username"),
                is_admin=tid in settings.admin_ids)
    session.add(user)
    await session.flush()
    acc = TelegramAccount(
        telegram_id=tid, user_id=user.id, username=tg.get("username"),
        first_name=tg.get("first_name"), language_code=tg.get("language_code"),
    )
    session.add(acc)
    await session.flush()
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    st_session: str | None = Cookie(default=None),
) -> User:
    """Resolve the caller. Mini App: validated initData header. Website: signed session cookie."""
    # 1) Telegram Mini App initData (validated server-side — never trust frontend user id)
    if x_init_data:
        try:
            data = validate_init_data(x_init_data)
        except InitDataError as exc:
            raise HTTPException(status_code=401, detail="invalid initData") from exc
        user = await _get_or_create_user_by_telegram(session, data["user"])
        if user.is_blocked:
            raise HTTPException(status_code=403, detail="blocked")
        return user

    # 2) Website session cookie (set after Telegram Login Widget verification)
    if st_session:
        from .security.signed_urls import _admin_serializer  # reuse serializer infra
        from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
        ser = URLSafeTimedSerializer(settings.SECRET_KEY, salt="sharetube-user-session")
        try:
            payload = ser.loads(st_session, max_age=30 * 24 * 3600)
            user = await session.get(User, int(payload["u"]))
            if user and not user.is_blocked:
                return user
        except (BadSignature, SignatureExpired, KeyError, ValueError):
            pass
    raise HTTPException(status_code=401, detail="authentication required")


def make_user_session(user_id: int) -> str:
    from itsdangerous import URLSafeTimedSerializer
    ser = URLSafeTimedSerializer(settings.SECRET_KEY, salt="sharetube-user-session")
    return ser.dumps({"u": user_id})


async def require_admin(
    session: AsyncSession = Depends(get_session),
    st_admin: str | None = Cookie(default=None),
) -> User:
    if not st_admin:
        raise HTTPException(status_code=401, detail="admin auth required")
    admin_id = verify_admin_session(st_admin)
    if not admin_id:
        raise HTTPException(status_code=401, detail="invalid admin session")
    user = await session.get(User, int(admin_id))
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="not an admin")
    return user


async def rate_limit_guard(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    ip = ip.split(",")[0].strip()
    if not await check_rate_limit(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
