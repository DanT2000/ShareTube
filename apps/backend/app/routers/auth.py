"""Authentication: Telegram Login Widget (website) and Mini App session bootstrap."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import SESSION_COOKIE, get_current_user, make_user_session, _get_or_create_user_by_telegram
from ..models import User
from ..schemas import TelegramAuthPayload
from ..security.telegram_auth import InitDataError, validate_login_widget

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram")
async def telegram_login(payload: TelegramAuthPayload, response: Response,
                         session: AsyncSession = Depends(get_session)):
    """Verify a Telegram Login Widget payload and set a signed session cookie."""
    try:
        data = validate_login_widget(payload.model_dump(exclude_none=True))
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail="invalid telegram auth") from exc
    user = await _get_or_create_user_by_telegram(session, data)
    await session.commit()
    secure = settings.PUBLIC_BASE_URL.startswith("https")
    response.set_cookie(
        SESSION_COOKIE, make_user_session(user.id), httponly=True, secure=secure,
        samesite="lax", max_age=30 * 24 * 3600,
    )
    return {"ok": True, "user_id": user.id, "is_admin": user.is_admin}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "display_name": user.display_name, "is_admin": user.is_admin}
