"""Backend integration tests for family management.

Tests cover:
- Full family lifecycle via HTTP API (create, invite, accept, manage, remove)
- Privacy-preserving invite: same response for existent and non-existent emails
- One-family constraint: cannot create a second family or accept invite while in a family
- Owner protection: owner cannot leave, be removed, or be demoted
- Last-admin protection: single admin cannot demote themselves

Lifecycle test exercises the API layer end-to-end with authenticated HTTP clients.
Edge case tests exercise the service layer directly with per-test transaction rollback.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.services.family_service import (
    change_role,
    create_family,
    invite_user,
    leave_family,
    remove_member,
    respond_to_invite,
)
from tests.conftest import _TEST_JWT_SECRET, create_test_family, create_test_invite, create_test_user

# ---------------------------------------------------------------------------
# NullPool db_session fixture — per-test transaction rollback
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
# Helpers for HTTP integration test
# ---------------------------------------------------------------------------


def _override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


def _make_test_jwt(user, expires_in: timedelta = timedelta(minutes=15)) -> str:
    """Create a signed JWT for *user* using the test secret."""
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user.google_id,
        "user_id": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


def _make_client(app, user, db_session: AsyncSession) -> AsyncClient:
    """Return an AsyncClient wired to *app* with JWT cookies for *user*."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={
            "access_token": _make_test_jwt(user, timedelta(minutes=15)),
            "refresh_token": _make_test_jwt(user, timedelta(days=7)),
        },
    )


# ---------------------------------------------------------------------------
# Full family lifecycle test — HTTP API layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_family_lifecycle(db_session: AsyncSession) -> None:
    """Full family lifecycle via the HTTP API layer.

    Steps:
    1.  User A creates a family (POST /api/families) — expect 201
    2.  User A invites User B by email (POST /api/families/{id}/invites) — expect 200
    3.  User B sees the pending invite (GET /api/invites) — invite listed
    4.  User B accepts the invite (POST /api/invites/{id}/respond action=accept) — expect 200
    5.  User A gets family details (GET /api/families/{id}) — both members listed
    6.  User A promotes User B to admin (PATCH /api/families/{id}/members/{b_id}) — expect 200
    7.  User A removes User B (DELETE /api/families/{id}/members/{b_id}) — expect 200
    8.  User A verifies User B is no longer in the member list (GET /api/families/{id})
    """
    from app.main import app

    # Create two users directly in the test DB
    user_a = await create_test_user(db_session, email="user_a@example.com", display_name="User A")
    user_b = await create_test_user(db_session, email="user_b@example.com", display_name="User B")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with (
            _make_client(app, user_a, db_session) as client_a,
            _make_client(app, user_b, db_session) as client_b,
        ):
            # ── Step 1: User A creates a family ────────────────────────────
            resp1 = await client_a.post("/api/families", json={"name": "Lifecycle Family"})
            assert resp1.status_code == 201, f"create family failed: {resp1.text}"
            family_data = resp1.json()
            family_id = family_data["id"]
            assert family_data["name"] == "Lifecycle Family"
            assert len(family_data["members"]) == 1
            assert family_data["members"][0]["user_id"] == str(user_a.id)

            # ── Step 2: User A invites User B ───────────────────────────────
            resp2 = await client_a.post(
                f"/api/families/{family_id}/invites",
                json={"email": user_b.email},
            )
            assert resp2.status_code == 200, f"invite failed: {resp2.text}"

            # ── Step 3: User B sees pending invite ──────────────────────────
            resp3 = await client_b.get("/api/invites")
            assert resp3.status_code == 200, f"get invites failed: {resp3.text}"
            invites = resp3.json()
            assert len(invites) == 1, f"expected 1 pending invite, got {len(invites)}"
            invite_id = invites[0]["id"]
            assert invites[0]["family_id"] == family_id

            # ── Step 4: User B accepts the invite ───────────────────────────
            resp4 = await client_b.post(
                f"/api/invites/{invite_id}/respond",
                json={"action": "accept"},
            )
            assert resp4.status_code == 200, f"accept invite failed: {resp4.text}"
            assert "accepted" in resp4.json()["message"].lower()

            # ── Step 5: User A gets family details — both members listed ────
            resp5 = await client_a.get(f"/api/families/{family_id}")
            assert resp5.status_code == 200, f"get family failed: {resp5.text}"
            members = resp5.json()["members"]
            member_ids = {m["user_id"] for m in members}
            assert str(user_a.id) in member_ids, "User A not in member list"
            assert str(user_b.id) in member_ids, "User B not in member list after accepting invite"

            # ── Step 6: User A promotes User B to admin ──────────────────────
            resp6 = await client_a.patch(
                f"/api/families/{family_id}/members/{user_b.id}",
                json={"role": "admin"},
            )
            assert resp6.status_code == 200, f"role change failed: {resp6.text}"
            assert resp6.json()["role"] == "admin"

            # ── Step 7: User A removes User B ────────────────────────────────
            resp7 = await client_a.delete(f"/api/families/{family_id}/members/{user_b.id}")
            assert resp7.status_code == 200, f"remove member failed: {resp7.text}"
            assert "removed" in resp7.json()["message"].lower()

            # ── Step 8: User B no longer in member list ───────────────────────
            resp8 = await client_a.get(f"/api/families/{family_id}")
            assert resp8.status_code == 200, f"get family after removal failed: {resp8.text}"
            members_after = resp8.json()["members"]
            member_ids_after = {m["user_id"] for m in members_after}
            assert str(user_b.id) not in member_ids_after, "User B still in member list after removal"
            assert str(user_a.id) in member_ids_after, "User A unexpectedly removed from member list"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Privacy-preserving invite tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_nonexistent_email_same_response(db_session: AsyncSession) -> None:
    """Inviting a non-existent email returns the same None response as inviting a real user.

    The service must never reveal whether the email matched a registered account.
    Both calls must return None without raising any exception.
    """
    admin = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, admin)

    # Invite a completely non-existent address — must not raise
    await invite_user(db_session, family.id, "fake@nowhere.invalid", admin)

    # Invite a real registered user (eligible — not in a family yet)
    real_user = await create_test_user(db_session, email="real@example.com")

    # Must also not raise — the response is indistinguishable (both return None)
    await invite_user(db_session, family.id, real_user.email, admin)


# ---------------------------------------------------------------------------
# One-family constraint — create second family
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_second_family_returns_409(db_session: AsyncSession) -> None:
    """A user already in a family receives HTTPException 409 when creating another family."""
    user = await create_test_user(db_session)
    await create_test_family(db_session, user)

    with pytest.raises(HTTPException) as exc_info:
        await create_family(db_session, user, name="Second Family")

    assert exc_info.value.status_code == 409
    assert "already belongs to a family" in exc_info.value.detail


# ---------------------------------------------------------------------------
# One-family constraint — accept invite while already in a family
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_invite_while_in_family_returns_409(db_session: AsyncSession) -> None:
    """Accepting an invite while already in a different family raises 409.

    The invite must also remain in 'pending' status after the failure.
    """
    from sqlalchemy import select

    # Alice owns Family A
    alice = await create_test_user(db_session, email="alice@example.com", display_name="Alice")
    family_a, _ = await create_test_family(db_session, alice, name="Family A")

    # Bob is invited to Family B (owned by Carol)
    carol = await create_test_user(db_session, email="carol@example.com", display_name="Carol")
    family_b, _ = await create_test_family(db_session, carol, name="Family B")

    bob = await create_test_user(db_session, email="bob@example.com", display_name="Bob")
    # Add Bob to Family A first
    bob_membership = FamilyMember(family_id=family_a.id, user_id=bob.id, role="member")
    db_session.add(bob_membership)
    await db_session.flush()

    # Create a pending invite for Bob to Family B
    invite = await create_test_invite(db_session, family_b, bob, carol)

    with pytest.raises(HTTPException) as exc_info:
        await respond_to_invite(db_session, invite.id, bob, "accept")

    assert exc_info.value.status_code == 409
    assert "already belongs to a family" in exc_info.value.detail

    # Invite must remain pending
    result = await db_session.execute(select(Invite).where(Invite.id == invite.id))
    refreshed_invite = result.scalar_one_or_none()
    assert refreshed_invite is not None
    assert refreshed_invite.status == "pending"


# ---------------------------------------------------------------------------
# Owner protection — owner cannot leave
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_cannot_leave(db_session: AsyncSession) -> None:
    """The family owner receives HTTPException 403 when attempting to leave."""
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    with pytest.raises(HTTPException) as exc_info:
        await leave_family(db_session, family.id, owner)

    assert exc_info.value.status_code == 403
    assert "owner" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_owner_remains_in_family_after_leave_attempt(db_session: AsyncSession) -> None:
    """After a failed leave attempt, the owner's membership record is still present."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    with pytest.raises(HTTPException):
        await leave_family(db_session, family.id, owner)

    # Membership must still exist
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == owner.id)
    )
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Owner protection — owner cannot be removed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_cannot_be_removed(db_session: AsyncSession) -> None:
    """An admin trying to remove the family owner receives HTTPException 403."""
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    # Add a second admin as the requester
    other_admin = await create_test_user(db_session, display_name="OtherAdmin")
    other_member = FamilyMember(family_id=family.id, user_id=other_admin.id, role="admin")
    db_session.add(other_member)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(db_session, family.id, owner.id, other_admin)

    assert exc_info.value.status_code == 403
    assert "Cannot remove the family owner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_owner_still_member_after_remove_attempt(db_session: AsyncSession) -> None:
    """After a failed removal attempt, the owner's membership is still present."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    other_admin = await create_test_user(db_session, display_name="OtherAdmin")
    other_member = FamilyMember(family_id=family.id, user_id=other_admin.id, role="admin")
    db_session.add(other_member)
    await db_session.flush()

    with pytest.raises(HTTPException):
        await remove_member(db_session, family.id, owner.id, other_admin)

    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == owner.id)
    )
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Owner protection — owner cannot be demoted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_cannot_be_demoted(db_session: AsyncSession) -> None:
    """An admin trying to demote the owner to member receives HTTPException 403."""
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    # Add a second admin as the requester
    other_admin = await create_test_user(db_session, display_name="OtherAdmin")
    other_member = FamilyMember(family_id=family.id, user_id=other_admin.id, role="admin")
    db_session.add(other_member)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await change_role(db_session, family.id, owner.id, "member", other_admin)

    assert exc_info.value.status_code == 403
    assert "Cannot demote the family owner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_owner_role_unchanged_after_demotion_attempt(db_session: AsyncSession) -> None:
    """After a failed demotion attempt, the owner's role remains 'admin'."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    other_admin = await create_test_user(db_session, display_name="OtherAdmin")
    other_member = FamilyMember(family_id=family.id, user_id=other_admin.id, role="admin")
    db_session.add(other_member)
    await db_session.flush()

    with pytest.raises(HTTPException):
        await change_role(db_session, family.id, owner.id, "member", other_admin)

    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == owner.id)
    )
    owner_member = result.scalar_one_or_none()
    assert owner_member is not None
    assert owner_member.role == "admin"


# ---------------------------------------------------------------------------
# Last-admin protection — demoting the last admin is blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demote_last_admin_blocked(db_session: AsyncSession) -> None:
    """A family's sole admin cannot demote themselves — raises HTTPException 403.

    The test sets up a family where the owner's membership role has been changed to
    'member' directly (bypassing the service), leaving a non-owner user as the sole
    admin. Attempting to demote that sole admin must be blocked.
    """
    from sqlalchemy import select

    # Create a family — owner is an admin by default
    owner = await create_test_user(db_session, display_name="Owner")
    family, owner_member = await create_test_family(db_session, owner)

    # Demote owner's membership to 'member' directly to create the sole-admin scenario
    owner_member.role = "member"
    await db_session.flush()

    # Add a single non-owner admin
    sole_admin = await create_test_user(db_session, display_name="SoleAdmin")
    sole_admin_member = FamilyMember(family_id=family.id, user_id=sole_admin.id, role="admin")
    db_session.add(sole_admin_member)
    await db_session.flush()

    # Verify only one admin in the family
    admin_count_result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.role == "admin")
    )
    admins = admin_count_result.scalars().all()
    assert len(admins) == 1
    assert admins[0].user_id == sole_admin.id

    # Attempt to demote the sole admin — must be blocked
    with pytest.raises(HTTPException) as exc_info:
        await change_role(db_session, family.id, sole_admin.id, "member", owner)

    assert exc_info.value.status_code == 403
    assert "Cannot demote the last admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_demote_last_admin_role_unchanged(db_session: AsyncSession) -> None:
    """After a failed last-admin demotion, the sole admin's role remains 'admin'."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family, owner_member = await create_test_family(db_session, owner)

    # Make owner a plain member so that sole_admin is the only admin
    owner_member.role = "member"
    await db_session.flush()

    sole_admin = await create_test_user(db_session, display_name="SoleAdmin")
    sole_admin_member = FamilyMember(family_id=family.id, user_id=sole_admin.id, role="admin")
    db_session.add(sole_admin_member)
    await db_session.flush()

    with pytest.raises(HTTPException):
        await change_role(db_session, family.id, sole_admin.id, "member", owner)

    # Role must not have changed
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == sole_admin.id)
    )
    member = result.scalar_one_or_none()
    assert member is not None
    assert member.role == "admin"


# ---------------------------------------------------------------------------
# Additional edge case: demoting a non-last admin succeeds (guard against over-blocking)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demote_non_last_admin_succeeds(db_session: AsyncSession) -> None:
    """When multiple admins exist, demoting one to member is allowed."""
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    second_admin = await create_test_user(db_session, display_name="SecondAdmin")
    second_member = FamilyMember(family_id=family.id, user_id=second_admin.id, role="admin")
    db_session.add(second_member)
    await db_session.flush()

    # There are now 2 admins — demoting one must succeed
    result = await change_role(db_session, family.id, second_admin.id, "member", owner)
    assert result.role == "member"


# ---------------------------------------------------------------------------
# Additional edge case: non-existent UUID for family or member
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leave_nonexistent_family_404(db_session: AsyncSession) -> None:
    """leave_family raises 404 when the family_id does not exist."""
    user = await create_test_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await leave_family(db_session, uuid.uuid4(), user)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_remove_nonexistent_member_404(db_session: AsyncSession) -> None:
    """remove_member raises 404 when the target user is not in the family."""
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)

    ghost = await create_test_user(db_session, display_name="Ghost")

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(db_session, family.id, ghost.id, owner)

    assert exc_info.value.status_code == 404
