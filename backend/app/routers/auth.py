"""Auth router: OAuth callback, token refresh, and logout endpoints."""

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.logging import get_logger
from app.models.refresh_token_blacklist import RefreshTokenBlacklist
from app.models.user import User
from app.schemas.auth import LoginCallbackRequest, LoginCallbackResponse
from app.services import google_oauth, user_service
from app.services.jwt_service import create_access_token, create_refresh_token, decode_token

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_SECURE = not settings.is_development


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=_COOKIE_SECURE,
        path="/api",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=_COOKIE_SECURE,
        path="/api/auth",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/api")
    response.delete_cookie(key="refresh_token", path="/api/auth")


@router.post("/callback", response_model=LoginCallbackResponse, status_code=status.HTTP_200_OK)
async def auth_callback(
    body: LoginCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginCallbackResponse:
    """Exchange Google authorization code for JWT session cookies.

    Accepts the PKCE authorization code + verifier from the frontend,
    exchanges it with Google, upserts the user, and sets HttpOnly JWT cookies.
    """
    try:
        id_token = await google_oauth.exchange_code(body.code, body.code_verifier)
        google_user = await google_oauth.verify_id_token(id_token)
    except Exception as exc:
        logger.warning("auth_callback_google_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication failed",
        )

    user, is_new_user = await user_service.upsert_user(
        google_id=google_user["sub"],
        email=google_user["email"],
        display_name=google_user.get("name", google_user["email"]),
        avatar_url=google_user.get("picture"),
        db=db,
    )

    _set_access_cookie(response, create_access_token(user))
    _set_refresh_cookie(response, create_refresh_token(user))

    logger.info("auth_callback_success", user_id=str(user.id), is_new_user=is_new_user)
    return LoginCallbackResponse(is_new_user=is_new_user)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def auth_refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issue a new access token using a valid, non-blacklisted refresh token."""
    if refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    try:
        payload = decode_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    jti: str = payload.get("jti", "")
    result = await db.execute(select(RefreshTokenBlacklist).where(RefreshTokenBlacklist.jti == jti))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    user_id_str: str = payload.get("user_id", "")
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    _set_access_cookie(response, create_access_token(user))
    logger.info("auth_refresh_success", user_id=str(user.id))
    return {"message": "Token refreshed"}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def auth_logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Blacklist the refresh token and clear all auth cookies."""
    if refresh_token is not None:
        try:
            payload = decode_token(refresh_token)
            jti: str = payload.get("jti", "")
            user_id_str: str = payload.get("user_id", "")
            exp_ts = payload.get("exp")

            if jti and user_id_str:
                expires_at = (
                    datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(tz=timezone.utc)
                )
                record = RefreshTokenBlacklist(
                    jti=jti,
                    user_id=uuid.UUID(user_id_str),
                    expires_at=expires_at,
                    created_at=datetime.now(tz=timezone.utc),
                )
                db.add(record)
                logger.info("auth_logout_blacklisted", jti=jti, user_id=user_id_str)
        except (jwt.InvalidTokenError, ValueError, Exception) as exc:
            # Log but don't fail logout if token is already invalid/expired
            logger.warning("auth_logout_token_error", error=str(exc))

    _clear_cookies(response)
    return {"message": "Logged out"}
