"""FastAPI dependencies for authentication and authorization."""

import uuid

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.logging import get_logger
from app.models.user import User
from app.services.jwt_service import decode_token

logger = get_logger(__name__)

_GENERIC_AUTH_ERROR = "Authentication required"


def _auth_error(detail: str) -> HTTPException:
    """Return a 401 HTTPException with environment-appropriate detail."""
    msg = detail if settings.is_development else _GENERIC_AUTH_ERROR
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: extract and validate the access_token cookie.

    Returns the authenticated :class:`~app.models.user.User` ORM object.
    Raises HTTP 401 on missing cookie, expired token, invalid signature, or
    user not found.
    """
    if access_token is None:
        logger.warning("auth_missing_cookie")
        raise _auth_error("Missing access_token cookie")

    try:
        payload = decode_token(access_token)
    except jwt.ExpiredSignatureError:
        logger.warning("auth_token_expired")
        raise _auth_error("Token has expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("auth_token_invalid", error=str(exc))
        raise _auth_error(f"Invalid token: {exc}")

    user_id_str: str | None = payload.get("user_id")
    if not user_id_str:
        logger.warning("auth_token_missing_user_id")
        raise _auth_error("Token missing user_id claim")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        logger.warning("auth_token_bad_user_id", user_id=user_id_str)
        raise _auth_error("Token contains invalid user_id")

    user = await db.get(User, user_id)
    if user is None:
        logger.warning("auth_user_not_found", user_id=user_id_str)
        raise _auth_error("User not found")

    return user
