"""JWT token creation and validation service."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings
from app.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

_ALGORITHM = "HS256"


def _build_payload(user: User, expires_in: timedelta) -> dict[str, Any]:
    """Build the standard JWT payload for *user*."""
    now = datetime.now(tz=timezone.utc)
    return {
        "sub": user.google_id,
        "user_id": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "jti": str(uuid.uuid4()),
    }


def create_access_token(user: User) -> str:
    """Return a signed access JWT for *user*.

    Lifetime comes from ``settings.jwt_access_token_expire_minutes`` (default 15).
    """
    payload = _build_payload(user, timedelta(minutes=settings.jwt_access_token_expire_minutes))
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)
    logger.info("access_token_created", user_id=str(user.id), jti=payload["jti"])
    return token


def create_refresh_token(user: User) -> str:
    """Return a signed refresh JWT for *user*.

    Lifetime comes from ``settings.jwt_refresh_token_expire_days`` (default 7).
    """
    payload = _build_payload(user, timedelta(days=settings.jwt_refresh_token_expire_days))
    token = jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)
    logger.info("refresh_token_created", user_id=str(user.id), jti=payload["jti"])
    return token


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate *token*.

    Returns the decoded payload dict.
    Raises :class:`jwt.PyJWTError` on invalid or expired tokens.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
