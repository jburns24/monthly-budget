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
from app.services.family_service import create_family, get_family_with_members
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
