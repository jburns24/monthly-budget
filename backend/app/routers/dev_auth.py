"""Dev-only auth bypass and test-reset endpoints.

These endpoints are only registered when ``settings.environment`` is
``"development"`` or ``"test"``.  They MUST NOT be reachable in production.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.refresh_token_blacklist import RefreshTokenBlacklist
from app.models.user import User
from app.services.jwt_service import create_access_token, create_refresh_token

logger = get_logger(__name__)

router = APIRouter(tags=["dev"])

_COOKIE_SECURE = False  # dev/test only — always HTTP


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class DevLoginRequest(BaseModel):
    email: str
    display_name: str


class DevLoginResponse(BaseModel):
    user_id: str
    email: str
    is_new_user: bool


# ---------------------------------------------------------------------------
# Helpers (mirror auth.py cookie helpers)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/auth/dev-login", response_model=DevLoginResponse, status_code=status.HTTP_200_OK)
async def dev_login(
    body: DevLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> DevLoginResponse:
    """Bypass Google OAuth: look up or create a user and issue JWT cookies.

    Accepts ``{ "email": "...", "display_name": "..." }`` and sets the same
    HttpOnly JWT cookies as the real OAuth callback so Playwright tests can
    authenticate without touching Google.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    now = datetime.now(tz=timezone.utc)
    is_new_user = user is None

    if user is None:
        user = User(
            google_id=f"dev-{uuid.uuid4().hex}",
            email=body.email,
            display_name=body.display_name,
            avatar_url=None,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()
        logger.info("dev_login_user_created", email=body.email)
    else:
        user.last_login_at = now
        user.display_name = body.display_name
        await db.flush()
        logger.info("dev_login_user_updated", email=body.email)

    _set_access_cookie(response, create_access_token(user))
    _set_refresh_cookie(response, create_refresh_token(user))

    return DevLoginResponse(
        user_id=str(user.id),
        email=user.email,
        is_new_user=is_new_user,
    )


@router.post("/api/test/reset", status_code=status.HTTP_200_OK)
async def test_reset(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Truncate test data tables in FK-safe order.

    Clears: invites → family_members → categories → families → users →
    refresh_token_blacklist.

    This endpoint enables idempotent e2e test suites — call it in
    ``beforeAll`` / ``beforeEach`` to start from a clean slate.
    """
    await db.execute(delete(Invite))
    await db.execute(delete(FamilyMember))
    # categories has FK to families (CASCADE), so delete categories before families.
    await db.execute(text("DELETE FROM categories"))
    # families has FK from family_members (cascade) and invites (cascade),
    # but we already deleted those rows above so we can delete families safely.
    await db.execute(text("DELETE FROM families"))
    await db.execute(delete(User))
    await db.execute(delete(RefreshTokenBlacklist))
    await db.flush()

    logger.info("test_reset_complete")
    return {"message": "Test data reset complete"}
