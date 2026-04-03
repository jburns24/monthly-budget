"""Tests for RBAC FastAPI dependencies: require_family_member and require_family_admin.

Each test exercises the dependencies via actual API endpoint calls using a
minimal test router mounted on the application, matching the authenticated_client
fixture pattern from conftest.py.
"""

from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.dependencies import require_family_admin, require_family_member
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User
from tests.conftest import _make_jwt, create_test_user

# ---------------------------------------------------------------------------
# NullPool db_session fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# DB override helper
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    """Return an async generator yielding *session* for the FastAPI DB dependency."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# Minimal test router that exercises the RBAC dependencies
# ---------------------------------------------------------------------------

_test_rbac_router = APIRouter(prefix="/test-rbac")


@_test_rbac_router.get("/families/{family_id}/member")
async def _member_endpoint(
    ctx: tuple[User, FamilyMember] = Depends(require_family_member),
) -> dict[str, Any]:
    user, member = ctx
    return {"user_id": str(user.id), "role": member.role}


@_test_rbac_router.get("/families/{family_id}/admin")
async def _admin_endpoint(
    ctx: tuple[User, FamilyMember] = Depends(require_family_admin),
) -> dict[str, Any]:
    user, member = ctx
    return {"user_id": str(user.id), "role": member.role}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_family_with_member(
    db: AsyncSession,
    user: User,
    role: str = "member",
) -> Family:
    """Create a Family and add *user* as a member with the given *role*."""
    family = Family(
        name="Test Family",
        created_by=user.id,
    )
    db.add(family)
    await db.flush()

    membership = FamilyMember(
        family_id=family.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    await db.flush()
    return family


def _make_client(app: Any, user: User) -> AsyncClient:
    """Return an AsyncClient pre-configured with a valid JWT cookie for *user*."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"access_token": _make_jwt(user, timedelta(minutes=15))},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_family_member_returns_user_and_member(db_session: AsyncSession) -> None:
    """require_family_member returns 200 with user_id and role for a valid member."""
    from app.main import app

    user = await create_test_user(db_session)
    family = await _create_family_with_member(db_session, user, role="member")

    app.include_router(_test_rbac_router)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with _make_client(app, user) as client:
            resp = await client.get(f"/test-rbac/families/{family.id}/member")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == str(user.id)
    assert body["role"] == "member"


@pytest.mark.asyncio
async def test_require_family_member_non_member_returns_404(db_session: AsyncSession) -> None:
    """require_family_member returns 404 when the user is not a member of the family."""
    from app.main import app

    user = await create_test_user(db_session)
    # Create the family but do NOT add *user* as a member
    other_user = await create_test_user(db_session)
    family = await _create_family_with_member(db_session, other_user, role="admin")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with _make_client(app, user) as client:
            resp = await client.get(f"/test-rbac/families/{family.id}/member")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Family not found"


@pytest.mark.asyncio
async def test_require_family_admin_returns_user_and_admin_member(db_session: AsyncSession) -> None:
    """require_family_admin returns 200 with user_id and role='admin' for an admin."""
    from app.main import app

    user = await create_test_user(db_session)
    family = await _create_family_with_member(db_session, user, role="admin")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with _make_client(app, user) as client:
            resp = await client.get(f"/test-rbac/families/{family.id}/admin")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == str(user.id)
    assert body["role"] == "admin"


@pytest.mark.asyncio
async def test_require_family_admin_member_non_admin_returns_403(db_session: AsyncSession) -> None:
    """require_family_admin returns 403 when the user is a member but not an admin."""
    from app.main import app

    user = await create_test_user(db_session)
    family = await _create_family_with_member(db_session, user, role="member")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with _make_client(app, user) as client:
            resp = await client.get(f"/test-rbac/families/{family.id}/admin")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


@pytest.mark.asyncio
async def test_require_family_admin_non_member_returns_404(db_session: AsyncSession) -> None:
    """require_family_admin returns 404 when the user is not a member at all."""
    from app.main import app

    user = await create_test_user(db_session)
    # Build a family the user is not part of
    other_user = await create_test_user(db_session)
    family = await _create_family_with_member(db_session, other_user, role="admin")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with _make_client(app, user) as client:
            resp = await client.get(f"/test-rbac/families/{family.id}/admin")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Family not found"
