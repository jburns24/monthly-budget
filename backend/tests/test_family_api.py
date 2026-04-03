"""API endpoint tests for all family routes.

Tests cover every family router endpoint using the authenticated_client fixture
with a NullPool database session override for per-test transaction rollback.

Endpoints tested:
  POST   /api/families                               — create family
  GET    /api/families/{family_id}                   — get family details
  POST   /api/families/{family_id}/invites           — invite user
  GET    /api/invites                                — list pending invites
  POST   /api/invites/{invite_id}/respond            — respond to invite
  DELETE /api/families/{family_id}/members/{user_id} — remove member
  PATCH  /api/families/{family_id}/members/{user_id} — change member role
  POST   /api/families/{family_id}/leave             — leave family
  GET    /api/me                                     — includes family field
"""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import _TEST_JWT_SECRET, create_test_family, create_test_invite, create_test_user

# ---------------------------------------------------------------------------
# NullPool db_session fixture — per-test transaction rollback
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback for isolation."""
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
# JWT patch fixture — ensures decode_token uses the same secret as the test JWTs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    """Patch app.services.jwt_service.settings so decode_token uses _TEST_JWT_SECRET.

    The authenticated_client fixture mints tokens with _TEST_JWT_SECRET.
    Without this patch the production settings.jwt_secret (empty string) is used
    and all token verifications fail with InvalidSignatureError.
    """
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


def _make_member(family_id, user_id, role: str = "member") -> FamilyMember:
    """Build a FamilyMember ORM object with joined_at set to now."""
    from datetime import datetime, timezone

    return FamilyMember(
        family_id=family_id,
        user_id=user_id,
        role=role,
        joined_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# POST /api/families
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_family_returns_201_with_details(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families with valid body returns 201 with family details."""
    from app.main import app

    user = await create_test_user(db_session)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post("/api/families", json={"name": "Burns Family", "timezone": "America/Chicago"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Burns Family"
    assert body["timezone"] == "America/Chicago"
    assert "id" in body
    assert "members" in body
    assert len(body["members"]) == 1
    assert body["members"][0]["role"] == "admin"
    assert body["created_by"] == str(user.id)


@pytest.mark.asyncio
async def test_create_family_user_already_in_family_returns_409(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families returns 409 when the user already belongs to a family."""
    from app.main import app

    user = await create_test_user(db_session)
    await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post("/api/families", json={"name": "Second Family"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_family_returns_member_list(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id} for a member returns 200 with member list."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    # Add a second member
    member_user = await create_test_user(db_session, display_name="Member")
    db_session.add(_make_member(family.id, member_user.id, role="member"))
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(owner) as client:
            resp = await client.get(f"/api/families/{family.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(family.id)
    assert len(body["members"]) == 2
    roles = {m["role"] for m in body["members"]}
    assert "admin" in roles
    assert "member" in roles


@pytest.mark.asyncio
async def test_get_family_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id} for a non-member returns 404 (not 403) to avoid leaking existence."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.get(f"/api/families/{family.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/invites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_returns_generic_success_valid_email(db_session: AsyncSession, authenticated_client) -> None:
    """POST invite with a real user email returns generic success message."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    invitee = await create_test_user(db_session, email="invitee@example.com")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(f"/api/families/{family.id}/invites", json={"email": invitee.email})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    assert "invite" in body["message"].lower() or "user" in body["message"].lower()


@pytest.mark.asyncio
async def test_invite_returns_generic_success_invalid_email(db_session: AsyncSession, authenticated_client) -> None:
    """POST invite with a non-existent email returns the same generic success message.

    The response must be indistinguishable from a valid-email invite (privacy-preserving).
    """
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/invites", json={"email": "nobody@nonexistent-test-domain.example.com"}
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Same status code and generic message — cannot tell if email existed
    assert resp.status_code == 200
    assert "message" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/invites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_invites_returns_pending_only(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/invites returns only the current user's pending invites."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    invitee = await create_test_user(db_session, display_name="Invitee")

    # Create a pending invite
    pending = await create_test_invite(db_session, family, invitee, admin)
    # Create a declined invite (should not appear)
    admin2 = await create_test_user(db_session, display_name="Admin2")
    family2, _ = await create_test_family(db_session, admin2)
    declined = await create_test_invite(db_session, family2, invitee, admin2, status="declined")  # noqa: F841

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(invitee) as client:
            resp = await client.get("/api/invites")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    invites = resp.json()
    # Only the pending invite should be returned
    assert len(invites) == 1
    assert invites[0]["id"] == str(pending.id)
    assert invites[0]["status"] == "pending"
    assert "family_name" in invites[0]
    assert "invited_by_name" in invites[0]


# ---------------------------------------------------------------------------
# POST /api/invites/{invite_id}/respond
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_invite_adds_member(db_session: AsyncSession, authenticated_client) -> None:
    """POST respond with accept adds the invitee as a family member."""
    from sqlalchemy import select

    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    invitee = await create_test_user(db_session, display_name="Invitee")
    invite = await create_test_invite(db_session, family, invitee, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(invitee) as client:
            resp = await client.post(f"/api/invites/{invite.id}/respond", json={"action": "accept"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert "accepted" in resp.json()["message"].lower()

    # Verify membership was created
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == invitee.id)
    )
    membership = result.scalar_one_or_none()
    assert membership is not None
    assert membership.role == "member"


@pytest.mark.asyncio
async def test_decline_invite_updates_status(db_session: AsyncSession, authenticated_client) -> None:
    """POST respond with decline updates invite status to declined."""
    from sqlalchemy import select

    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    invitee = await create_test_user(db_session, display_name="Invitee")
    invite = await create_test_invite(db_session, family, invitee, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(invitee) as client:
            resp = await client.post(f"/api/invites/{invite.id}/respond", json={"action": "decline"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert "declined" in resp.json()["message"].lower()

    # Verify invite status was updated
    result = await db_session.execute(select(Invite).where(Invite.id == invite.id))
    updated_invite = result.scalar_one_or_none()
    assert updated_invite is not None
    assert updated_invite.status == "declined"

    # Verify invitee did NOT become a member
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == invitee.id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# DELETE /api/families/{family_id}/members/{user_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_member_removes_member(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE member as admin removes the member from the family."""
    from sqlalchemy import select

    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    regular_user = await create_test_user(db_session, display_name="Regular")
    db_session.add(_make_member(family.id, regular_user.id))
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.delete(f"/api/families/{family.id}/members/{regular_user.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert "removed" in resp.json()["message"].lower()

    # Verify membership was deleted
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == regular_user.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_member_non_admin_returns_403(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE member as non-admin returns 403 Forbidden."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    regular_user = await create_test_user(db_session, display_name="Regular")
    db_session.add(_make_member(family.id, regular_user.id))

    another_user = await create_test_user(db_session, display_name="Another")
    db_session.add(_make_member(family.id, another_user.id))
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        # regular_user (non-admin) tries to remove another_user
        async with authenticated_client(regular_user) as client:
            resp = await client.delete(f"/api/families/{family.id}/members/{another_user.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/families/{family_id}/members/{user_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_role_changes_role(db_session: AsyncSession, authenticated_client) -> None:
    """PATCH role as admin promotes member to admin successfully."""
    from sqlalchemy import select

    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    regular_user = await create_test_user(db_session, display_name="Regular")
    db_session.add(_make_member(family.id, regular_user.id))
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.patch(
                f"/api/families/{family.id}/members/{regular_user.id}",
                json={"role": "admin"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["user_id"] == str(regular_user.id)

    # Confirm DB state
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == regular_user.id)
    )
    updated = result.scalar_one_or_none()
    assert updated is not None
    assert updated.role == "admin"


@pytest.mark.asyncio
async def test_patch_role_last_admin_demotion_blocked(db_session: AsyncSession, authenticated_client) -> None:
    """PATCH demoting the last admin returns 403 Forbidden."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, owner_member = await create_test_family(db_session, owner)

    # Demote owner to plain member directly to make sole_admin the only admin
    owner_member.role = "member"
    await db_session.flush()

    sole_admin = await create_test_user(db_session, display_name="SoleAdmin")
    db_session.add(_make_member(family.id, sole_admin.id, role="admin"))
    await db_session.flush()

    # owner (now a plain member) tries to demote sole_admin — but owner has no admin role
    # so we need another admin to perform the action. Let's use sole_admin trying to demote themselves.
    # Actually require_family_admin checks current user — owner is a member, so returns 403.
    # Use sole_admin to attempt the demote (as if they have admin access to do the patch):
    # The route requires admin role — sole_admin IS an admin, so the route proceeds.
    # Then the service blocks the demotion as last admin.
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(sole_admin) as client:
            resp = await client.patch(
                f"/api/families/{family.id}/members/{sole_admin.id}",
                json={"role": "member"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/leave
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leave_family_success(db_session: AsyncSession, authenticated_client) -> None:
    """POST leave as non-owner member successfully removes them from the family."""
    from sqlalchemy import select

    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    regular_user = await create_test_user(db_session, display_name="Regular")
    db_session.add(_make_member(family.id, regular_user.id))
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(regular_user) as client:
            resp = await client.post(f"/api/families/{family.id}/leave")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert "left" in resp.json()["message"].lower()

    # Verify membership removed
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == regular_user.id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# GET /api/me — family field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_includes_family_info(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/me returns a family field when the user belongs to a family."""
    from app.main import app

    user = await create_test_user(db_session, display_name="FamilyMember")
    family, _ = await create_test_family(db_session, user, name="Test Family")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get("/api/me")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["family"] is not None
    assert body["family"]["id"] == str(family.id)
    assert body["family"]["name"] == "Test Family"
    assert body["family"]["role"] == "admin"


@pytest.mark.asyncio
async def test_get_me_no_family_returns_null(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/me returns family: null when the user has no family membership."""
    from app.main import app

    user = await create_test_user(db_session, display_name="Loner")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get("/api/me")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "family" in body
    assert body["family"] is None
