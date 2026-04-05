"""Unit tests for the category_service module.

Tests exercise all public service functions directly against the database,
verifying correct return values, error handling, and idempotency.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.category import Category
from app.models.expense import Expense
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from app.services.category_service import (
    _DEFAULT_CATEGORIES,
    create_category,
    delete_category,
    list_active_categories,
    seed_default_categories,
    update_category,
)
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


async def _make_family(db: AsyncSession) -> Family:
    """Create a test user and family, returning the family."""
    owner = await create_test_user(db)
    family, _ = await create_test_family(db, owner)
    return family


async def _insert_category(
    db: AsyncSession,
    family: Family,
    name: str = "Groceries",
    icon: str | None = "cart",
    sort_order: int = 0,
    is_active: bool = True,
) -> Category:
    """Insert a Category row directly and return the ORM object."""
    cat = Category(
        family_id=family.id,
        name=name,
        icon=icon,
        sort_order=sort_order,
        is_active=is_active,
    )
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return cat


# ---------------------------------------------------------------------------
# create_category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_category_returns_orm_with_correct_fields(db_session: AsyncSession) -> None:
    """create_category returns a Category ORM with the expected field values."""
    family = await _make_family(db_session)

    cat = await create_category(db_session, family.id, name="Dining", icon="fork", sort_order=3)

    assert isinstance(cat, Category)
    assert cat.family_id == family.id
    assert cat.name == "Dining"
    assert cat.icon == "fork"
    assert cat.sort_order == 3
    assert cat.is_active is True
    assert isinstance(cat.id, uuid.UUID)
    assert cat.created_at is not None


@pytest.mark.asyncio
async def test_create_category_icon_can_be_none(db_session: AsyncSession) -> None:
    """create_category accepts icon=None and stores NULL."""
    family = await _make_family(db_session)

    cat = await create_category(db_session, family.id, name="Savings", icon=None)

    assert cat.icon is None


@pytest.mark.asyncio
async def test_create_category_sort_order_defaults_to_zero(db_session: AsyncSession) -> None:
    """create_category uses sort_order=0 when omitted."""
    family = await _make_family(db_session)

    cat = await create_category(db_session, family.id, name="Bills", icon=None)

    assert cat.sort_order == 0


@pytest.mark.asyncio
async def test_create_category_duplicate_name_raises_409(db_session: AsyncSession) -> None:
    """create_category raises HTTPException(409) when name already exists in the family."""
    family = await _make_family(db_session)
    await _insert_category(db_session, family, name="Groceries")

    with pytest.raises(HTTPException) as exc_info:
        await create_category(db_session, family.id, name="Groceries", icon=None)

    assert exc_info.value.status_code == 409
    assert "Groceries" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_category_same_name_different_family_succeeds(db_session: AsyncSession) -> None:
    """create_category allows the same name in a different family."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)

    cat1 = await create_category(db_session, family1.id, name="Transport", icon=None)
    cat2 = await create_category(db_session, family2.id, name="Transport", icon=None)

    assert cat1.name == cat2.name
    assert cat1.family_id != cat2.family_id


# ---------------------------------------------------------------------------
# list_active_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_active_categories_returns_only_active(db_session: AsyncSession) -> None:
    """list_active_categories excludes archived (is_active=False) categories."""
    family = await _make_family(db_session)
    await _insert_category(db_session, family, name="Active One", is_active=True)
    await _insert_category(db_session, family, name="Archived", is_active=False)

    results = await list_active_categories(db_session, family.id)

    names = [c.name for c in results]
    assert "Active One" in names
    assert "Archived" not in names


@pytest.mark.asyncio
async def test_list_active_categories_sorted_by_sort_order_then_name(db_session: AsyncSession) -> None:
    """list_active_categories returns categories ordered by sort_order ASC then name ASC."""
    family = await _make_family(db_session)
    await _insert_category(db_session, family, name="Zebra", sort_order=1)
    await _insert_category(db_session, family, name="Apple", sort_order=2)
    await _insert_category(db_session, family, name="Mango", sort_order=1)

    results = await list_active_categories(db_session, family.id)

    assert [c.name for c in results] == ["Mango", "Zebra", "Apple"]


@pytest.mark.asyncio
async def test_list_active_categories_empty_when_none_exist(db_session: AsyncSession) -> None:
    """list_active_categories returns an empty list when the family has no active categories."""
    family = await _make_family(db_session)

    results = await list_active_categories(db_session, family.id)

    assert results == []


@pytest.mark.asyncio
async def test_list_active_categories_excludes_other_families(db_session: AsyncSession) -> None:
    """list_active_categories only returns categories belonging to the requested family."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)

    await _insert_category(db_session, family1, name="Family1 Cat")
    await _insert_category(db_session, family2, name="Family2 Cat")

    results = await list_active_categories(db_session, family1.id)

    names = [c.name for c in results]
    assert "Family1 Cat" in names
    assert "Family2 Cat" not in names


# ---------------------------------------------------------------------------
# update_category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_category_name_only(db_session: AsyncSession) -> None:
    """update_category with only name updates the name, leaving other fields unchanged."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, name="Old Name", icon="star", sort_order=5)

    updated = await update_category(db_session, family.id, cat.id, name="New Name", icon=None, sort_order=None)

    assert updated.name == "New Name"
    assert updated.icon == "star"
    assert updated.sort_order == 5


@pytest.mark.asyncio
async def test_update_category_icon_only(db_session: AsyncSession) -> None:
    """update_category with only icon updates the icon, leaving other fields unchanged."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, name="Transport", icon="car", sort_order=2)

    updated = await update_category(db_session, family.id, cat.id, name=None, icon="bus", sort_order=None)

    assert updated.name == "Transport"
    assert updated.icon == "bus"
    assert updated.sort_order == 2


@pytest.mark.asyncio
async def test_update_category_sort_order_only(db_session: AsyncSession) -> None:
    """update_category with only sort_order updates the sort_order, leaving other fields unchanged."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, name="Entertainment", icon="film", sort_order=0)

    updated = await update_category(db_session, family.id, cat.id, name=None, icon=None, sort_order=99)

    assert updated.name == "Entertainment"
    assert updated.icon == "film"
    assert updated.sort_order == 99


@pytest.mark.asyncio
async def test_update_category_not_found_raises_404(db_session: AsyncSession) -> None:
    """update_category raises HTTPException(404) when the category does not exist."""
    family = await _make_family(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await update_category(db_session, family.id, uuid.uuid4(), name="X", icon=None, sort_order=None)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_category_wrong_family_raises_404(db_session: AsyncSession) -> None:
    """update_category raises HTTPException(404) when category belongs to a different family."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)
    cat = await _insert_category(db_session, family1, name="MyCategory")

    with pytest.raises(HTTPException) as exc_info:
        await update_category(db_session, family2.id, cat.id, name="Hacked", icon=None, sort_order=None)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_category_duplicate_name_raises_409(db_session: AsyncSession) -> None:
    """update_category raises HTTPException(409) when the new name conflicts with an existing category."""
    family = await _make_family(db_session)
    await _insert_category(db_session, family, name="Existing")
    cat = await _insert_category(db_session, family, name="Target")

    with pytest.raises(HTTPException) as exc_info:
        await update_category(db_session, family.id, cat.id, name="Existing", icon=None, sort_order=None)

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# delete_category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_category_hard_deletes_when_no_expenses(db_session: AsyncSession) -> None:
    """delete_category returns {'deleted': True} and removes the row when no expenses exist."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, name="ToDelete")
    cat_id = cat.id

    result = await delete_category(db_session, family.id, cat_id)

    assert result == {"deleted": True}
    fetched = await db_session.get(Category, cat_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_category_not_found_raises_404(db_session: AsyncSession) -> None:
    """delete_category raises HTTPException(404) when the category does not exist."""
    family = await _make_family(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await delete_category(db_session, family.id, uuid.uuid4())

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_category_wrong_family_raises_404(db_session: AsyncSession) -> None:
    """delete_category raises HTTPException(404) when category belongs to a different family."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)
    cat = await _insert_category(db_session, family1, name="Protected")

    with pytest.raises(HTTPException) as exc_info:
        await delete_category(db_session, family2.id, cat.id)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_category_archives_when_expenses_exist(db_session: AsyncSession) -> None:
    """delete_category returns archived result and sets is_active=False when expenses reference it."""
    family = await _make_family(db_session)
    owner = await create_test_user(db_session)
    cat = await _insert_category(db_session, family, name="WithExpenses")

    # Insert an expense referencing this category
    expense = Expense(
        family_id=family.id,
        category_id=cat.id,
        user_id=owner.id,
        amount_cents=1000,
        description="Test expense",
    )
    db_session.add(expense)
    await db_session.flush()

    result = await delete_category(db_session, family.id, cat.id)

    assert result == {"deleted": False, "archived": True, "expense_count": 1}
    await db_session.refresh(cat)
    assert cat.is_active is False


# ---------------------------------------------------------------------------
# seed_default_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_default_categories_creates_six(db_session: AsyncSession) -> None:
    """seed_default_categories creates exactly 6 categories for a new family."""
    family = await _make_family(db_session)

    created_count = await seed_default_categories(db_session, family.id)

    assert created_count == 6


@pytest.mark.asyncio
async def test_seed_default_categories_correct_names_and_icons(db_session: AsyncSession) -> None:
    """seed_default_categories creates categories with the correct names and icons."""
    family = await _make_family(db_session)
    await seed_default_categories(db_session, family.id)

    result = await db_session.execute(select(Category).where(Category.family_id == family.id))
    categories = {c.name: c for c in result.scalars().all()}

    expected_names = {name for name, _, _ in _DEFAULT_CATEGORIES}
    assert set(categories.keys()) == expected_names

    for name, icon, sort_order in _DEFAULT_CATEGORIES:
        assert categories[name].icon == icon
        assert categories[name].sort_order == sort_order


@pytest.mark.asyncio
async def test_seed_default_categories_idempotent(db_session: AsyncSession) -> None:
    """seed_default_categories is idempotent: second call creates 0 new categories."""
    family = await _make_family(db_session)

    first = await seed_default_categories(db_session, family.id)
    second = await seed_default_categories(db_session, family.id)

    assert first == 6
    assert second == 0

    result = await db_session.execute(select(Category).where(Category.family_id == family.id))
    assert len(result.scalars().all()) == 6


@pytest.mark.asyncio
async def test_seed_default_categories_skips_existing_names(db_session: AsyncSession) -> None:
    """seed_default_categories skips categories whose names already exist."""
    family = await _make_family(db_session)
    # Pre-create one of the defaults
    await _insert_category(db_session, family, name="Groceries")

    created_count = await seed_default_categories(db_session, family.id)

    assert created_count == 5


@pytest.mark.asyncio
async def test_seed_default_categories_all_active(db_session: AsyncSession) -> None:
    """seed_default_categories creates all categories with is_active=True."""
    family = await _make_family(db_session)
    await seed_default_categories(db_session, family.id)

    result = await db_session.execute(select(Category).where(Category.family_id == family.id))
    categories = result.scalars().all()

    assert all(c.is_active is True for c in categories)
