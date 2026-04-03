"""FastAPI dependencies for authentication and authorization."""

import uuid

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.logging import get_logger
from app.models.family_member import FamilyMember
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


async def require_family_member(
    family_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, FamilyMember]:
    """FastAPI dependency: verify the current user is a member of the given family.

    Returns ``(current_user, family_member)`` on success.
    Raises HTTP 404 with "Family not found" if the user is not a member —
    intentionally uses 404 (not 403) to avoid leaking whether the family exists.
    """
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == current_user.id,
        )
    )
    family_member = result.scalar_one_or_none()
    if family_member is None:
        logger.warning(
            "rbac_family_member_not_found",
            family_id=str(family_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")
    return current_user, family_member


async def require_family_admin(
    family_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, FamilyMember]:
    """FastAPI dependency: verify the current user is an admin of the given family.

    Returns ``(current_user, family_member)`` on success.
    Raises HTTP 404 if the user is not a member of the family, or HTTP 403
    if the user is a member but does not have the ``admin`` role.
    """
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == current_user.id,
        )
    )
    family_member = result.scalar_one_or_none()
    if family_member is None:
        logger.warning(
            "rbac_family_admin_member_not_found",
            family_id=str(family_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")
    if family_member.role != "admin":
        logger.warning(
            "rbac_family_admin_insufficient_role",
            family_id=str(family_id),
            user_id=str(current_user.id),
            role=family_member.role,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user, family_member
