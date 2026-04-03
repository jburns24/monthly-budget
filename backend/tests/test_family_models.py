"""Unit tests for Family, FamilyMember, and Invite ORM models.

These tests verify that the models map correctly to the database schema,
including field types, constraints, defaults, and relationships.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User
from tests.conftest import create_test_user

# ---------------------------------------------------------------------------
# Local fixture: NullPool engine avoids event-loop conflicts across tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test NullPool engine and transaction rollback.

    Using NullPool prevents asyncpg connections from being re-used across
    pytest-asyncio's per-function event loops, eliminating 'Future attached
    to a different loop' errors.
    """
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
# Helpers
# ---------------------------------------------------------------------------


async def create_test_family(db: AsyncSession, owner: User, **overrides) -> Family:
    """Insert a Family into the test database and return the ORM object."""
    now = datetime.now(tz=timezone.utc)
    unique = uuid.uuid4().hex[:8]
    defaults = {
        "id": uuid.uuid4(),
        "name": f"Test Family {unique}",
        "timezone": "America/New_York",
        "edit_grace_days": 7,
        "created_by": owner.id,
        "created_at": now,
    }
    defaults.update(overrides)
    family = Family(**defaults)
    db.add(family)
    await db.flush()
    await db.refresh(family)
    return family


async def create_test_member(db: AsyncSession, family: Family, user: User, role: str = "member") -> FamilyMember:
    """Insert a FamilyMember into the test database and return the ORM object."""
    now = datetime.now(tz=timezone.utc)
    member = FamilyMember(
        id=uuid.uuid4(),
        family_id=family.id,
        user_id=user.id,
        role=role,
        joined_at=now,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


async def create_test_invite(
    db: AsyncSession,
    family: Family,
    invited_user: User,
    invited_by: User,
    status: str = "pending",
) -> Invite:
    """Insert an Invite into the test database and return the ORM object."""
    now = datetime.now(tz=timezone.utc)
    invite = Invite(
        id=uuid.uuid4(),
        family_id=family.id,
        invited_user_id=invited_user.id,
        invited_by=invited_by.id,
        status=status,
        created_at=now,
    )
    db.add(invite)
    await db.flush()
    await db.refresh(invite)
    return invite


# ---------------------------------------------------------------------------
# Family model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_family(db_session: AsyncSession) -> None:
    """Family record can be inserted and retrieved with all columns intact."""
    owner = await create_test_user(db_session)
    now = datetime.now(tz=timezone.utc)
    family_id = uuid.uuid4()

    family = Family(
        id=family_id,
        name="Smith Family",
        timezone="America/Chicago",
        edit_grace_days=14,
        created_by=owner.id,
        created_at=now,
    )
    db_session.add(family)
    await db_session.flush()
    await db_session.refresh(family)

    fetched = await db_session.get(Family, family_id)
    assert fetched is not None
    assert fetched.id == family_id
    assert fetched.name == "Smith Family"
    assert fetched.timezone == "America/Chicago"
    assert fetched.edit_grace_days == 14
    assert fetched.created_by == owner.id
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_family_defaults(db_session: AsyncSession) -> None:
    """Family.timezone defaults to 'America/New_York' and edit_grace_days defaults to 7."""
    owner = await create_test_user(db_session)
    family = Family(name="Default Family", created_by=owner.id)
    db_session.add(family)
    await db_session.flush()
    await db_session.refresh(family)

    assert family.timezone == "America/New_York"
    assert family.edit_grace_days == 7
    assert family.id is not None
    assert isinstance(family.id, uuid.UUID)


# ---------------------------------------------------------------------------
# FamilyMember model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_family_member(db_session: AsyncSession) -> None:
    """FamilyMember record can be inserted and retrieved with correct columns and FK to Family."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session)
    now = datetime.now(tz=timezone.utc)
    member_id = uuid.uuid4()

    member = FamilyMember(
        id=member_id,
        family_id=family.id,
        user_id=member_user.id,
        role="admin",
        joined_at=now,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(member)

    fetched = await db_session.get(FamilyMember, member_id)
    assert fetched is not None
    assert fetched.id == member_id
    assert fetched.family_id == family.id
    assert fetched.user_id == member_user.id
    assert fetched.role == "admin"
    assert fetched.joined_at is not None


@pytest.mark.asyncio
async def test_family_member_unique_constraint(db_session: AsyncSession) -> None:
    """Inserting duplicate (family_id, user_id) raises IntegrityError."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    user = await create_test_user(db_session)

    # Insert the first member successfully.
    await create_test_member(db_session, family, user)

    # Attempt to insert a duplicate — must raise.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                FamilyMember(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    user_id=user.id,
                    role="member",
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_family_member_role_check(db_session: AsyncSession) -> None:
    """Inserting a FamilyMember with an invalid role raises IntegrityError."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    user = await create_test_user(db_session)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                FamilyMember(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    user_id=user.id,
                    role="superadmin",  # invalid
                )
            )
            await db_session.flush()


# ---------------------------------------------------------------------------
# Invite model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_invite(db_session: AsyncSession) -> None:
    """Invite record can be inserted and retrieved with all columns correct."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    invited = await create_test_user(db_session)
    now = datetime.now(tz=timezone.utc)
    invite_id = uuid.uuid4()

    invite = Invite(
        id=invite_id,
        family_id=family.id,
        invited_user_id=invited.id,
        invited_by=owner.id,
        status="pending",
        created_at=now,
    )
    db_session.add(invite)
    await db_session.flush()
    await db_session.refresh(invite)

    fetched = await db_session.get(Invite, invite_id)
    assert fetched is not None
    assert fetched.id == invite_id
    assert fetched.family_id == family.id
    assert fetched.invited_user_id == invited.id
    assert fetched.invited_by == owner.id
    assert fetched.status == "pending"
    assert fetched.created_at is not None
    assert fetched.responded_at is None


@pytest.mark.asyncio
async def test_invite_status_check(db_session: AsyncSession) -> None:
    """Inserting an Invite with an invalid status raises IntegrityError."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    invited = await create_test_user(db_session)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Invite(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    invited_user_id=invited.id,
                    invited_by=owner.id,
                    status="rejected",  # invalid — only pending/accepted/declined are valid
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_invite_unique_constraint(db_session: AsyncSession) -> None:
    """Inserting duplicate (family_id, invited_user_id, status) raises IntegrityError."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    invited = await create_test_user(db_session)

    # First pending invite — should succeed.
    await create_test_invite(db_session, family, invited, owner, status="pending")

    # Second pending invite for the same (family, user) — must raise.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Invite(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    invited_user_id=invited.id,
                    invited_by=owner.id,
                    status="pending",
                )
            )
            await db_session.flush()


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_family_memberships_relationship(db_session: AsyncSession) -> None:
    """User.family_memberships returns the related FamilyMember records."""
    owner = await create_test_user(db_session)
    family1 = await create_test_family(db_session, owner)
    family2 = await create_test_family(db_session, owner)
    await create_test_member(db_session, family1, owner, role="admin")
    await create_test_member(db_session, family2, owner, role="member")

    db_session.expunge_all()
    fetched_user = await db_session.get(User, owner.id)
    assert fetched_user is not None

    result = await db_session.execute(select(FamilyMember).where(FamilyMember.user_id == owner.id))
    memberships = result.scalars().all()
    assert len(memberships) == 2
    family_ids = {m.family_id for m in memberships}
    assert family1.id in family_ids
    assert family2.id in family_ids


@pytest.mark.asyncio
async def test_family_members_relationship(db_session: AsyncSession) -> None:
    """Family.members returns the related FamilyMember records."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    user2 = await create_test_user(db_session)
    user3 = await create_test_user(db_session)

    await create_test_member(db_session, family, owner, role="admin")
    await create_test_member(db_session, family, user2, role="member")
    await create_test_member(db_session, family, user3, role="member")

    result = await db_session.execute(select(FamilyMember).where(FamilyMember.family_id == family.id))
    members = result.scalars().all()
    assert len(members) == 3
    user_ids = {m.user_id for m in members}
    assert owner.id in user_ids
    assert user2.id in user_ids
    assert user3.id in user_ids


@pytest.mark.asyncio
async def test_family_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Family cascades to delete its family_members and invites."""
    owner = await create_test_user(db_session)
    family = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session)
    invited_user = await create_test_user(db_session)

    member = await create_test_member(db_session, family, owner, role="admin")
    member2 = await create_test_member(db_session, family, member_user, role="member")
    invite = await create_test_invite(db_session, family, invited_user, owner)

    member_id = member.id
    member2_id = member2.id
    invite_id = invite.id
    family_id = family.id

    # Delete the family — cascades should remove members and invites.
    fetched_family = await db_session.get(Family, family_id)
    await db_session.delete(fetched_family)
    await db_session.flush()
    db_session.expunge_all()

    assert await db_session.get(Family, family_id) is None
    assert await db_session.get(FamilyMember, member_id) is None
    assert await db_session.get(FamilyMember, member2_id) is None
    assert await db_session.get(Invite, invite_id) is None
