"""Unit tests for the Category ORM model.

These tests verify that the Category model maps correctly to the database
schema, including field types, constraints, defaults, and relationships.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.category import Category
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from tests.conftest import create_test_family, create_test_user

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


async def create_test_category(db: AsyncSession, family: Family, **overrides) -> Category:
    """Insert a Category into the test database and return the ORM object."""
    unique = uuid.uuid4().hex[:8]
    defaults = {
        "id": uuid.uuid4(),
        "family_id": family.id,
        "name": f"Test Category {unique}",
        "icon": None,
        "sort_order": 0,
        "is_active": True,
    }
    defaults.update(overrides)
    category = Category(**defaults)
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


# ---------------------------------------------------------------------------
# Category model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_retrieve_category(db_session: AsyncSession) -> None:
    """Category can be created and retrieved with all fields intact."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category_id = uuid.uuid4()

    category = Category(
        id=category_id,
        family_id=family.id,
        name="Groceries",
        icon="cart",
        sort_order=5,
        is_active=True,
    )
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    fetched = await db_session.get(Category, category_id)
    assert fetched is not None
    assert fetched.id == category_id
    assert fetched.family_id == family.id
    assert fetched.name == "Groceries"
    assert fetched.icon == "cart"
    assert fetched.sort_order == 5
    assert fetched.is_active is True
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_category_is_active_defaults_to_true(db_session: AsyncSession) -> None:
    """Category.is_active defaults to True when not specified."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    category = Category(
        family_id=family.id,
        name="Utilities",
    )
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    assert category.is_active is True


@pytest.mark.asyncio
async def test_category_sort_order_defaults_to_zero(db_session: AsyncSession) -> None:
    """Category.sort_order defaults to 0 when not specified."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    category = Category(
        family_id=family.id,
        name="Transport",
    )
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    assert category.sort_order == 0


@pytest.mark.asyncio
async def test_category_id_auto_generated(db_session: AsyncSession) -> None:
    """Category.id is auto-generated as a UUID when not provided."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    category = Category(
        family_id=family.id,
        name="Entertainment",
    )
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    assert category.id is not None
    assert isinstance(category.id, uuid.UUID)


@pytest.mark.asyncio
async def test_category_unique_constraint_raises_on_duplicate(db_session: AsyncSession) -> None:
    """UNIQUE(family_id, name) constraint raises IntegrityError on duplicate."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    # Insert first category — succeeds.
    await create_test_category(db_session, family, name="Dining")

    # Insert duplicate (same family_id + name) — must raise.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Category(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    name="Dining",
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_category_unique_constraint_allows_same_name_different_family(db_session: AsyncSession) -> None:
    """Same category name is allowed across different families."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)

    cat1 = await create_test_category(db_session, family1, name="Groceries")
    cat2 = await create_test_category(db_session, family2, name="Groceries")

    assert cat1.name == cat2.name
    assert cat1.family_id != cat2.family_id


@pytest.mark.asyncio
async def test_category_cascade_delete_with_family(db_session: AsyncSession) -> None:
    """Deleting a Family cascades to delete its categories."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    cat1 = await create_test_category(db_session, family, name="Rent")
    cat2 = await create_test_category(db_session, family, name="Groceries")
    cat1_id = cat1.id
    cat2_id = cat2.id
    family_id = family.id

    # Delete the family — cascade must remove categories.
    fetched_family = await db_session.get(Family, family_id)
    await db_session.delete(fetched_family)
    await db_session.flush()
    db_session.expunge_all()

    assert await db_session.get(Family, family_id) is None
    assert await db_session.get(Category, cat1_id) is None
    assert await db_session.get(Category, cat2_id) is None


@pytest.mark.asyncio
async def test_category_icon_is_nullable(db_session: AsyncSession) -> None:
    """Category.icon is nullable and can be omitted."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    category = await create_test_category(db_session, family, name="Savings", icon=None)

    assert category.icon is None


@pytest.mark.asyncio
async def test_category_family_relationship(db_session: AsyncSession) -> None:
    """Category.family relationship resolves to the parent Family."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    category = await create_test_category(db_session, family, name="Insurance")

    # Query categories for this family via select to avoid lazy-load issues.
    result = await db_session.execute(select(Category).where(Category.family_id == family.id))
    categories = result.scalars().all()
    assert len(categories) == 1
    assert categories[0].id == category.id
    assert categories[0].family_id == family.id
