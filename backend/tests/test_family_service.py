"""Unit tests for FamilyService: create_family and get_family_with_members.

Each test uses a NullPool db_session that rolls back after the test,
keeping the database clean between runs.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.services.family_service import (
    change_role,
    create_family,
    get_family_with_members,
    invite_user,
    leave_family,
    remove_member,
    respond_to_invite,
)
from tests.conftest import create_test_user

# ---------------------------------------------------------------------------
# Local fixture: NullPool engine avoids event-loop conflicts across tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test NullPool engine and transaction rollback."""
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
# create_family tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_family_success(db_session: AsyncSession) -> None:
    """create_family creates the family and an admin membership for the user."""
    user = await create_test_user(db_session)

    family = await create_family(db_session, user, name="Smith Family", timezone="America/Chicago")

    assert family.id is not None
    assert isinstance(family.id, uuid.UUID)
    assert family.name == "Smith Family"
    assert family.timezone == "America/Chicago"
    assert family.created_by == user.id

    # Verify admin membership was created — re-query to avoid stale state
    from sqlalchemy import select

    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == user.id)
    )
    membership = result.scalar_one_or_none()
    assert membership is not None
    assert membership.role == "admin"
    assert membership.user_id == user.id


@pytest.mark.asyncio
async def test_create_family_user_already_in_family(db_session: AsyncSession) -> None:
    """create_family raises 409 if the user already belongs to a family."""
    user = await create_test_user(db_session)

    # Create first family — succeeds
    await create_family(db_session, user, name="First Family")

    # Attempt to create a second family — must raise 409
    with pytest.raises(HTTPException) as exc_info:
        await create_family(db_session, user, name="Second Family")

    assert exc_info.value.status_code == 409
    assert "already belongs to a family" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_family_default_timezone(db_session: AsyncSession) -> None:
    """create_family uses 'America/New_York' as the default timezone."""
    user = await create_test_user(db_session)

    family = await create_family(db_session, user, name="Default TZ Family")

    assert family.timezone == "America/New_York"


# ---------------------------------------------------------------------------
# get_family_with_members tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_family_with_members(db_session: AsyncSession) -> None:
    """get_family_with_members returns the family with members and their users populated."""
    user = await create_test_user(db_session, display_name="Alice", email="alice@example.com")
    family = await create_family(db_session, user, name="Alice Family")

    fetched = await get_family_with_members(db_session, family.id)

    assert fetched is not None
    assert fetched.id == family.id
    assert fetched.name == "Alice Family"
    assert len(fetched.members) == 1
    assert fetched.members[0].user_id == user.id
    assert fetched.members[0].role == "admin"
    # User relationship is eagerly loaded
    assert fetched.members[0].user is not None
    assert fetched.members[0].user.display_name == "Alice"


@pytest.mark.asyncio
async def test_get_family_with_members_multiple_members(db_session: AsyncSession) -> None:
    """get_family_with_members returns all members when multiple exist."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Multi Family")

    # Add a second member directly
    second_user = await create_test_user(db_session, display_name="Member")
    second_membership = FamilyMember(
        family_id=family.id,
        user_id=second_user.id,
        role="member",
    )
    db_session.add(second_membership)
    await db_session.flush()

    fetched = await get_family_with_members(db_session, family.id)

    assert len(fetched.members) == 2
    member_names = {m.user.display_name for m in fetched.members}
    assert member_names == {"Owner", "Member"}


@pytest.mark.asyncio
async def test_get_family_with_members_not_found(db_session: AsyncSession) -> None:
    """get_family_with_members raises 404 for an unknown family_id."""
    non_existent_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await get_family_with_members(db_session, non_existent_id)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# invite_user tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_user_nonexistent_email_succeeds_silently(db_session: AsyncSession) -> None:
    """invite_user returns None and creates no invite when the email is unknown."""
    from sqlalchemy import select

    inviter = await create_test_user(db_session)
    family = await create_family(db_session, inviter, name="Invite Family")

    # No user with this email exists — must not raise
    await invite_user(db_session, family.id, "nobody@nowhere.invalid", inviter)

    # Confirm no invite was created
    invite_rows = await db_session.execute(select(Invite).where(Invite.family_id == family.id))
    assert invite_rows.scalars().all() == []


@pytest.mark.asyncio
async def test_invite_user_already_in_family_succeeds_silently(db_session: AsyncSession) -> None:
    """invite_user returns None and creates no invite when the target user is already in a family."""
    from sqlalchemy import select

    inviter = await create_test_user(db_session)
    family = await create_family(db_session, inviter, name="Invite Family 2")

    # Create a second user who already belongs to their own family
    target = await create_test_user(db_session, email="already@example.com")
    target_family = await create_family(db_session, target, name="Target Family")
    _ = target_family  # suppress unused-variable warning

    # Must not raise even though user is already in a family
    await invite_user(db_session, family.id, "already@example.com", inviter)

    # Confirm no invite to family was created for target
    invite_rows = await db_session.execute(
        select(Invite).where(Invite.family_id == family.id, Invite.invited_user_id == target.id)
    )
    assert invite_rows.scalars().all() == []


@pytest.mark.asyncio
async def test_invite_user_already_has_pending_invite_succeeds_silently(db_session: AsyncSession) -> None:
    """invite_user returns None and creates no duplicate invite when one is already pending."""
    from sqlalchemy import select

    inviter = await create_test_user(db_session)
    family = await create_family(db_session, inviter, name="Invite Family 3")
    target = await create_test_user(db_session, email="pending@example.com")

    # First invite — should succeed and create an invite
    await invite_user(db_session, family.id, "pending@example.com", inviter)

    # Second invite for the same user — must not raise (silently does nothing)
    await invite_user(db_session, family.id, "pending@example.com", inviter)

    # Only one pending invite should exist
    invite_rows = await db_session.execute(
        select(Invite).where(
            Invite.family_id == family.id,
            Invite.invited_user_id == target.id,
            Invite.status == "pending",
        )
    )
    invites = invite_rows.scalars().all()
    assert len(invites) == 1


@pytest.mark.asyncio
async def test_invite_user_valid_email_creates_invite(db_session: AsyncSession) -> None:
    """invite_user creates a pending Invite record when the target user is eligible."""
    from sqlalchemy import select

    inviter = await create_test_user(db_session)
    family = await create_family(db_session, inviter, name="Invite Family 4")
    target = await create_test_user(db_session, email="eligible@example.com")

    # Must not raise when user is eligible
    await invite_user(db_session, family.id, "eligible@example.com", inviter)

    # Verify the invite was created with correct fields
    invite_row = await db_session.execute(
        select(Invite).where(
            Invite.family_id == family.id,
            Invite.invited_user_id == target.id,
        )
    )
    invite = invite_row.scalar_one_or_none()
    assert invite is not None
    assert invite.status == "pending"
    assert invite.invited_user_id == target.id
    assert invite.invited_by == inviter.id
    assert invite.family_id == family.id


# ---------------------------------------------------------------------------
# respond_to_invite tests
# ---------------------------------------------------------------------------


async def _create_pending_invite(db_session: AsyncSession) -> tuple:
    """Helper: create a family with an owner and a pending invite for a target user."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Invite Family")
    target = await create_test_user(db_session, email="invitee@example.com", display_name="Invitee")

    invite = Invite(
        family_id=family.id,
        invited_user_id=target.id,
        invited_by=owner.id,
        status="pending",
    )
    db_session.add(invite)
    await db_session.flush()
    return owner, family, target, invite


@pytest.mark.asyncio
async def test_respond_to_invite_accept_adds_member(db_session: AsyncSession) -> None:
    """Accepting an invite adds the user as a member and marks the invite accepted."""
    from sqlalchemy import select

    _owner, family, target, invite = await _create_pending_invite(db_session)

    result = await respond_to_invite(db_session, invite.id, target, "accept")

    assert result.status == "accepted"
    assert result.responded_at is not None

    # Verify membership was created
    member_row = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == target.id)
    )
    member = member_row.scalar_one_or_none()
    assert member is not None
    assert member.role == "member"


@pytest.mark.asyncio
async def test_respond_to_invite_accept_already_in_family_409(db_session: AsyncSession) -> None:
    """Accepting an invite raises 409 if user already belongs to a family."""
    _owner, _family, target, invite = await _create_pending_invite(db_session)

    # Put the target in another family first
    other_owner = await create_test_user(db_session, display_name="Other Owner")
    other_family = await create_family(db_session, other_owner, name="Other Family")
    member = FamilyMember(family_id=other_family.id, user_id=target.id, role="member")
    db_session.add(member)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await respond_to_invite(db_session, invite.id, target, "accept")

    assert exc_info.value.status_code == 409
    assert "already belongs to a family" in exc_info.value.detail


@pytest.mark.asyncio
async def test_respond_to_invite_decline_updates_status(db_session: AsyncSession) -> None:
    """Declining an invite updates status to declined and sets responded_at."""
    _owner, _family, target, invite = await _create_pending_invite(db_session)

    result = await respond_to_invite(db_session, invite.id, target, "decline")

    assert result.status == "declined"
    assert result.responded_at is not None


# ---------------------------------------------------------------------------
# remove_member tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_member_success(db_session: AsyncSession) -> None:
    """remove_member deletes a non-owner member from the family."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Remove Family")

    target = await create_test_user(db_session, display_name="Target")
    member = FamilyMember(family_id=family.id, user_id=target.id, role="member")
    db_session.add(member)
    await db_session.flush()

    await remove_member(db_session, family.id, target.id, owner)

    # Verify member is removed
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == target.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_remove_member_owner_blocked_403(db_session: AsyncSession) -> None:
    """remove_member raises 403 when trying to remove the family owner."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Remove Owner Family")

    # Add a second admin to be the requester
    admin2 = await create_test_user(db_session, display_name="Admin2")
    member = FamilyMember(family_id=family.id, user_id=admin2.id, role="admin")
    db_session.add(member)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(db_session, family.id, owner.id, admin2)

    assert exc_info.value.status_code == 403
    assert "Cannot remove the family owner" in exc_info.value.detail


# ---------------------------------------------------------------------------
# change_role tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_role_success(db_session: AsyncSession) -> None:
    """change_role promotes a member to admin."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Role Family")

    target = await create_test_user(db_session, display_name="Target")
    member = FamilyMember(family_id=family.id, user_id=target.id, role="member")
    db_session.add(member)
    await db_session.flush()

    result = await change_role(db_session, family.id, target.id, "admin", owner)

    assert result.role == "admin"


@pytest.mark.asyncio
async def test_change_role_demote_owner_blocked_403(db_session: AsyncSession) -> None:
    """change_role raises 403 when demoting the family owner."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Demote Owner Family")

    # Add second admin as requester
    admin2 = await create_test_user(db_session, display_name="Admin2")
    member = FamilyMember(family_id=family.id, user_id=admin2.id, role="admin")
    db_session.add(member)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await change_role(db_session, family.id, owner.id, "member", admin2)

    assert exc_info.value.status_code == 403
    assert "Cannot demote the family owner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_change_role_demote_last_admin_blocked_403(db_session: AsyncSession) -> None:
    """change_role raises 403 when demoting the last admin (who is not the owner)."""
    # Create family where created_by is a different user than the sole admin
    creator = await create_test_user(db_session, display_name="Creator")
    family = await create_family(db_session, creator, name="Last Admin Family")

    # Creator is admin. Add a second user as member.
    second = await create_test_user(db_session, display_name="Second")
    member = FamilyMember(family_id=family.id, user_id=second.id, role="member")
    db_session.add(member)
    await db_session.flush()

    # Try demoting the creator (the only admin) who is also the owner -- 403 owner check
    # Instead, let's set up a non-owner admin as the only admin
    # Create a fresh scenario: owner + one non-owner admin, then remove owner's admin status
    owner2 = await create_test_user(db_session, display_name="Owner2")
    family2 = await create_family(db_session, owner2, name="Last Admin Family 2")

    non_owner_admin = await create_test_user(db_session, display_name="NonOwnerAdmin")
    admin_member = FamilyMember(family_id=family2.id, user_id=non_owner_admin.id, role="admin")
    db_session.add(admin_member)
    await db_session.flush()

    # Now there are 2 admins (owner2 and non_owner_admin). Demote owner2's membership is blocked (owner).
    # Demote non_owner_admin when there are 2 admins should succeed.
    result = await change_role(db_session, family2.id, non_owner_admin.id, "member", owner2)
    assert result.role == "member"

    # Now re-promote non_owner_admin and then demote owner2-as-only-admin scenario won't work
    # because owner2 IS the owner. Let's build a proper "last admin" scenario:
    # family3 with owner3, and a second admin who we then demote leaving only 1 admin
    owner3 = await create_test_user(db_session, display_name="Owner3")
    family3 = await create_family(db_session, owner3, name="Last Admin Family 3")

    solo_admin = await create_test_user(db_session, display_name="SoloAdmin")
    solo_member = FamilyMember(family_id=family3.id, user_id=solo_admin.id, role="admin")
    db_session.add(solo_member)
    await db_session.flush()

    # Demote one admin (solo_admin) -- this works since there are 2 admins
    await change_role(db_session, family3.id, solo_admin.id, "member", owner3)

    # Re-promote solo_admin
    await change_role(db_session, family3.id, solo_admin.id, "admin", owner3)

    # Now demote owner3 (blocked as owner, not last admin)
    # We need: only 1 admin who is NOT the owner. Let's demote owner3... no, owner is protected.

    # Simplest approach: create a scenario where owner has role=member (manually) and
    # only 1 admin exists who is not the owner.
    owner4 = await create_test_user(db_session, display_name="Owner4")
    family4 = await create_family(db_session, owner4, name="Last Admin Family 4")

    # owner4 is admin. Change owner4 role to member directly (bypassing service to set up scenario).
    from sqlalchemy import select as sel

    owner4_member_result = await db_session.execute(
        sel(FamilyMember).where(FamilyMember.family_id == family4.id, FamilyMember.user_id == owner4.id)
    )
    owner4_member = owner4_member_result.scalar_one()
    owner4_member.role = "member"
    await db_session.flush()

    # Add a single admin who is not the owner
    last_admin = await create_test_user(db_session, display_name="LastAdmin")
    last_admin_member = FamilyMember(family_id=family4.id, user_id=last_admin.id, role="admin")
    db_session.add(last_admin_member)
    await db_session.flush()

    # Now try to demote the last admin
    with pytest.raises(HTTPException) as exc_info:
        await change_role(db_session, family4.id, last_admin.id, "member", owner4)

    assert exc_info.value.status_code == 403
    assert "Cannot demote the last admin" in exc_info.value.detail


# ---------------------------------------------------------------------------
# leave_family tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leave_family_success(db_session: AsyncSession) -> None:
    """leave_family removes the member record for a non-owner user."""
    from sqlalchemy import select

    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Leave Family")

    leaver = await create_test_user(db_session, display_name="Leaver")
    member = FamilyMember(family_id=family.id, user_id=leaver.id, role="member")
    db_session.add(member)
    await db_session.flush()

    await leave_family(db_session, family.id, leaver)

    # Verify member is gone
    result = await db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == leaver.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_leave_family_owner_blocked_403(db_session: AsyncSession) -> None:
    """leave_family raises 403 when the owner tries to leave."""
    owner = await create_test_user(db_session, display_name="Owner")
    family = await create_family(db_session, owner, name="Owner Leave Family")

    with pytest.raises(HTTPException) as exc_info:
        await leave_family(db_session, family.id, owner)

    assert exc_info.value.status_code == 403
    assert "owner cannot leave" in exc_info.value.detail.lower()
