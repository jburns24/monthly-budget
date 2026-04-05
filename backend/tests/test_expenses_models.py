"""Unit tests for the Expense and MonthlyGoal ORM models.

These tests verify that the models map correctly to the database schema,
including field types, constraints, defaults, and relationships.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.category import Category
from app.models.expense import Expense
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from tests.conftest import create_test_category, create_test_expense, create_test_family, create_test_user

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
# Expense model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_create_and_retrieve_all_fields(db_session: AsyncSession) -> None:
    """Expense can be created and retrieved with all fields intact."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    expense_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)

    expense = Expense(
        id=expense_id,
        family_id=family.id,
        category_id=category.id,
        user_id=owner.id,
        amount_cents=4523,
        description="Groceries",
        expense_date=date(2026, 4, 1),
        year_month="2026-04",
        created_at=now,
        updated_at=now,
    )
    db_session.add(expense)
    await db_session.flush()
    await db_session.refresh(expense)

    fetched = await db_session.get(Expense, expense_id)
    assert fetched is not None
    assert fetched.id == expense_id
    assert fetched.family_id == family.id
    assert fetched.category_id == category.id
    assert fetched.user_id == owner.id
    assert fetched.amount_cents == 4523
    assert fetched.description == "Groceries"
    assert fetched.expense_date == date(2026, 4, 1)
    assert fetched.year_month == "2026-04"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_expense_year_month_is_populated(db_session: AsyncSession) -> None:
    """year_month field can be set and retrieved correctly from expense_date."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    expense = Expense(
        family_id=family.id,
        category_id=category.id,
        user_id=owner.id,
        amount_cents=1000,
        description="Test",
        expense_date=date(2026, 4, 1),
        year_month=date(2026, 4, 1).strftime("%Y-%m"),
        created_at=now,
        updated_at=now,
    )
    db_session.add(expense)
    await db_session.flush()
    await db_session.refresh(expense)

    assert expense.year_month == "2026-04"


@pytest.mark.asyncio
async def test_expense_amount_cents_check_constraint_rejects_zero(db_session: AsyncSession) -> None:
    """amount_cents CHECK constraint rejects zero values."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Expense(
                    family_id=family.id,
                    category_id=category.id,
                    user_id=owner.id,
                    amount_cents=0,
                    description="Zero amount",
                    expense_date=date(2026, 4, 1),
                    year_month="2026-04",
                    created_at=now,
                    updated_at=now,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_expense_amount_cents_check_constraint_rejects_negative(db_session: AsyncSession) -> None:
    """amount_cents CHECK constraint rejects negative values."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Expense(
                    family_id=family.id,
                    category_id=category.id,
                    user_id=owner.id,
                    amount_cents=-100,
                    description="Negative amount",
                    expense_date=date(2026, 4, 1),
                    year_month="2026-04",
                    created_at=now,
                    updated_at=now,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_expense_cascade_delete_with_family(db_session: AsyncSession) -> None:
    """Deleting a Family cascades to delete its expenses (DB-level CASCADE).

    Uses a raw DELETE statement to bypass SQLAlchemy ORM-level cascade ordering,
    which would otherwise conflict with the RESTRICT constraint on category->expenses.
    The database-level CASCADE on expenses.family_id ensures expenses are removed.
    """
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    expense1 = await create_test_expense(db_session, family, owner, category)
    expense2 = await create_test_expense(db_session, family, owner, category)
    expense1_id = expense1.id
    expense2_id = expense2.id
    family_id = family.id

    # Expunge all ORM objects so the session does not try to re-insert them.
    db_session.expunge_all()

    # Use raw DELETE to let the DB-level CASCADE remove expenses (and members/categories).
    await db_session.execute(delete(Family).where(Family.id == family_id))
    await db_session.flush()

    assert await db_session.get(Family, family_id) is None
    assert await db_session.get(Expense, expense1_id) is None
    assert await db_session.get(Expense, expense2_id) is None


@pytest.mark.asyncio
async def test_expense_restrict_prevents_category_deletion(db_session: AsyncSession) -> None:
    """RESTRICT constraint prevents category deletion when expenses reference it."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    await create_test_expense(db_session, family, owner, category)

    # Attempt to delete the category — RESTRICT must raise.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            fetched_category = await db_session.get(Category, category.id)
            await db_session.delete(fetched_category)
            await db_session.flush()


@pytest.mark.asyncio
async def test_expense_id_auto_generated(db_session: AsyncSession) -> None:
    """Expense.id is auto-generated as a UUID when not provided."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(db_session, family, owner, category)

    assert expense.id is not None
    assert isinstance(expense.id, uuid.UUID)


@pytest.mark.asyncio
async def test_expense_description_defaults_to_empty_string(db_session: AsyncSession) -> None:
    """Expense.description defaults to empty string when not provided."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    expense = Expense(
        family_id=family.id,
        category_id=category.id,
        user_id=owner.id,
        amount_cents=500,
        expense_date=date(2026, 4, 1),
        year_month="2026-04",
        created_at=now,
        updated_at=now,
    )
    db_session.add(expense)
    await db_session.flush()
    await db_session.refresh(expense)

    assert expense.description == ""


@pytest.mark.asyncio
async def test_expense_receipt_id_is_nullable(db_session: AsyncSession) -> None:
    """Expense.receipt_id is nullable and can be omitted."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(db_session, family, owner, category)

    assert expense.receipt_id is None


@pytest.mark.asyncio
async def test_expense_query_by_family_and_year_month(db_session: AsyncSession) -> None:
    """Expenses can be queried by family_id and year_month."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(db_session, family, owner, category, year_month="2026-04")

    result = await db_session.execute(
        select(Expense).where(Expense.family_id == family.id, Expense.year_month == "2026-04")
    )
    expenses = result.scalars().all()
    assert len(expenses) == 1
    assert expenses[0].id == expense.id


# ---------------------------------------------------------------------------
# MonthlyGoal model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monthly_goal_create_and_retrieve_all_fields(db_session: AsyncSession) -> None:
    """MonthlyGoal can be created and retrieved with all fields intact."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    goal_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)

    goal = MonthlyGoal(
        id=goal_id,
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()
    await db_session.refresh(goal)

    fetched = await db_session.get(MonthlyGoal, goal_id)
    assert fetched is not None
    assert fetched.id == goal_id
    assert fetched.family_id == family.id
    assert fetched.category_id == category.id
    assert fetched.year_month == "2026-04"
    assert fetched.amount_cents == 50000
    assert fetched.version == 1
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_monthly_goal_unique_constraint_raises_on_duplicate(db_session: AsyncSession) -> None:
    """UNIQUE(family_id, category_id, year_month) raises IntegrityError on duplicate."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    # Insert first goal — succeeds.
    first_goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(first_goal)
    await db_session.flush()

    # Insert duplicate (same family_id, category_id, year_month) — must raise.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                MonthlyGoal(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    category_id=category.id,
                    year_month="2026-04",
                    amount_cents=60000,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_monthly_goal_unique_constraint_allows_different_month(db_session: AsyncSession) -> None:
    """Same family+category is allowed for different year_month values."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    goal_apr = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    goal_may = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-05",
        amount_cents=55000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal_apr)
    db_session.add(goal_may)
    await db_session.flush()
    await db_session.refresh(goal_apr)
    await db_session.refresh(goal_may)

    assert goal_apr.year_month == "2026-04"
    assert goal_may.year_month == "2026-05"


@pytest.mark.asyncio
async def test_monthly_goal_unique_constraint_allows_different_category(db_session: AsyncSession) -> None:
    """Same family+month is allowed for different categories."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category1 = await create_test_category(db_session, family, name="Groceries")
    category2 = await create_test_category(db_session, family, name="Dining")
    now = datetime.now(tz=timezone.utc)

    goal1 = MonthlyGoal(
        family_id=family.id,
        category_id=category1.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    goal2 = MonthlyGoal(
        family_id=family.id,
        category_id=category2.id,
        year_month="2026-04",
        amount_cents=30000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal1)
    db_session.add(goal2)
    await db_session.flush()
    await db_session.refresh(goal1)
    await db_session.refresh(goal2)

    assert goal1.category_id != goal2.category_id


@pytest.mark.asyncio
async def test_monthly_goal_cascade_delete_with_family(db_session: AsyncSession) -> None:
    """Deleting a Family cascades to delete its monthly goals."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()
    await db_session.refresh(goal)
    goal_id = goal.id
    family_id = family.id

    # Delete the family — cascade must remove monthly goals.
    fetched_family = await db_session.get(Family, family_id)
    await db_session.delete(fetched_family)
    await db_session.flush()
    db_session.expunge_all()

    assert await db_session.get(Family, family_id) is None
    assert await db_session.get(MonthlyGoal, goal_id) is None


@pytest.mark.asyncio
async def test_monthly_goal_id_auto_generated(db_session: AsyncSession) -> None:
    """MonthlyGoal.id is auto-generated as a UUID when not provided."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=50000,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()
    await db_session.refresh(goal)

    assert goal.id is not None
    assert isinstance(goal.id, uuid.UUID)


@pytest.mark.asyncio
async def test_monthly_goal_amount_cents_is_nullable(db_session: AsyncSession) -> None:
    """MonthlyGoal.amount_cents is nullable (goal may not be set yet)."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)
    now = datetime.now(tz=timezone.utc)

    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=None,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()
    await db_session.refresh(goal)

    assert goal.amount_cents is None
