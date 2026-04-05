"""Unit tests for the expense_service module.

Tests exercise all public service functions directly against the database,
verifying correct return values, error handling, and edge cases.

Each test uses a local db_session fixture with NullPool to avoid event-loop
conflicts with pytest-asyncio's per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.expense import Expense
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from app.services.category_service import _count_category_expenses
from app.services.expense_service import (
    create_expense,
    delete_expense,
    get_budget_summary,
    list_expenses,
    update_expense,
)
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
# Helpers
# ---------------------------------------------------------------------------


async def _make_family(db: AsyncSession) -> tuple[Family, User]:
    """Create a test user and family, returning (family, user)."""
    owner = await create_test_user(db)
    family, _ = await create_test_family(db, owner)
    return family, owner


# ---------------------------------------------------------------------------
# create_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_expense_succeeds_with_valid_inputs(db_session: AsyncSession) -> None:
    """create_expense returns an Expense with correct fields and eager-loaded relationships."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    expense = await create_expense(
        db_session,
        family_id=family.id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=4523,
        description="Weekly shop",
        expense_date=date(2026, 4, 1),
    )

    assert isinstance(expense, Expense)
    assert expense.amount_cents == 4523
    assert expense.year_month == "2026-04"
    assert expense.description == "Weekly shop"
    assert expense.family_id == family.id
    assert expense.user_id == user.id
    assert expense.category_id == category.id
    # Eager-loaded relationships
    assert expense.category is not None
    assert expense.category.id == category.id
    assert expense.user is not None
    assert expense.user.id == user.id


@pytest.mark.asyncio
async def test_create_expense_rejects_inactive_category(db_session: AsyncSession) -> None:
    """create_expense raises HTTPException(400) when the category is inactive."""
    family, user = await _make_family(db_session)
    inactive_category = await create_test_category(db_session, family, is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        await create_expense(
            db_session,
            family_id=family.id,
            user_id=user.id,
            category_id=inactive_category.id,
            amount_cents=1000,
            description="Test",
            expense_date=date(2026, 4, 1),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_expense_rejects_nonexistent_category(db_session: AsyncSession) -> None:
    """create_expense raises HTTPException(400) when the category does not exist."""
    family, user = await _make_family(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await create_expense(
            db_session,
            family_id=family.id,
            user_id=user.id,
            category_id=uuid.uuid4(),
            amount_cents=1000,
            description="Test",
            expense_date=date(2026, 4, 1),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_expense_computes_year_month(db_session: AsyncSession) -> None:
    """create_expense computes year_month from expense_date."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    expense = await create_expense(
        db_session,
        family_id=family.id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=2500,
        description="December purchase",
        expense_date=date(2025, 12, 15),
    )

    assert expense.year_month == "2025-12"


# ---------------------------------------------------------------------------
# list_expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_expenses_filters_by_year_month(db_session: AsyncSession) -> None:
    """list_expenses returns only expenses matching the requested year_month."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    # 3 expenses in April, 2 in March
    for _ in range(3):
        await create_test_expense(
            db_session, family, user, category, year_month="2026-04", expense_date=date(2026, 4, 1)
        )
    for _ in range(2):
        await create_test_expense(
            db_session, family, user, category, year_month="2026-03", expense_date=date(2026, 3, 1)
        )

    expenses, total_count = await list_expenses(db_session, family.id, year_month="2026-04")

    assert len(expenses) == 3
    assert total_count == 3
    assert all(e.year_month == "2026-04" for e in expenses)


@pytest.mark.asyncio
async def test_list_expenses_pagination(db_session: AsyncSession) -> None:
    """list_expenses returns the correct page and total_count when paginating."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    # Create 75 expenses
    for i in range(75):
        await create_test_expense(
            db_session,
            family,
            user,
            category,
            year_month="2026-04",
            expense_date=date(2026, 4, 1),
            amount_cents=100 + i,
        )

    expenses, total_count = await list_expenses(db_session, family.id, year_month="2026-04", page=2, per_page=50)

    assert len(expenses) == 25
    assert total_count == 75


@pytest.mark.asyncio
async def test_list_expenses_filters_by_category(db_session: AsyncSession) -> None:
    """list_expenses filters by category_id when provided."""
    family, user = await _make_family(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")
    transport = await create_test_category(db_session, family, name="Transport")

    for _ in range(3):
        await create_test_expense(db_session, family, user, groceries, year_month="2026-04")
    for _ in range(2):
        await create_test_expense(db_session, family, user, transport, year_month="2026-04")

    expenses, total_count = await list_expenses(db_session, family.id, year_month="2026-04", category_id=groceries.id)

    assert len(expenses) == 3
    assert total_count == 3
    assert all(e.category_id == groceries.id for e in expenses)


# ---------------------------------------------------------------------------
# update_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_expense_partial_fields(db_session: AsyncSession) -> None:
    """update_expense changes only the provided fields, leaving others unchanged."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)
    expense = await create_test_expense(
        db_session, family, user, category, amount_cents=4523, description="Weekly shop"
    )

    updated = await update_expense(
        db_session,
        family_id=family.id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        description="Monthly shop",
    )

    assert updated.description == "Monthly shop"
    assert updated.amount_cents == 4523
    assert updated.updated_at >= expense.updated_at


@pytest.mark.asyncio
async def test_update_expense_optimistic_locking_409(db_session: AsyncSession) -> None:
    """update_expense raises HTTPException(409) when expected_updated_at does not match."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)
    expense = await create_test_expense(db_session, family, user, category)

    stale_updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        await update_expense(
            db_session,
            family_id=family.id,
            expense_id=expense.id,
            expected_updated_at=stale_updated_at,
            description="Should fail",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_update_expense_recomputes_year_month(db_session: AsyncSession) -> None:
    """update_expense recomputes year_month when expense_date is changed."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)
    expense = await create_test_expense(
        db_session, family, user, category, expense_date=date(2026, 4, 1), year_month="2026-04"
    )

    updated = await update_expense(
        db_session,
        family_id=family.id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        expense_date=date(2026, 3, 15),
    )

    assert updated.year_month == "2026-03"


# ---------------------------------------------------------------------------
# delete_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_expense_removes_from_database(db_session: AsyncSession) -> None:
    """delete_expense hard-deletes the expense from the database."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)
    expense = await create_test_expense(db_session, family, user, category)
    expense_id = expense.id

    await delete_expense(db_session, family_id=family.id, expense_id=expense_id)

    result = await db_session.execute(select(Expense).where(Expense.id == expense_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_expense_raises_404_when_not_found(db_session: AsyncSession) -> None:
    """delete_expense raises HTTPException(404) for a nonexistent expense id."""
    family, _ = await _make_family(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await delete_expense(db_session, family_id=family.id, expense_id=uuid.uuid4())

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_budget_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_summary_aggregates_spending_per_category(db_session: AsyncSession) -> None:
    """get_budget_summary returns correct spent_cents and status per category."""
    family, user = await _make_family(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")
    transport = await create_test_category(db_session, family, name="Transport")

    # 3 Groceries expenses totaling 15000 cents
    for amount in (5000, 5000, 5000):
        await create_test_expense(db_session, family, user, groceries, amount_cents=amount, year_month="2026-04")

    # 1 Transport expense of 2500 cents
    await create_test_expense(db_session, family, user, transport, amount_cents=2500, year_month="2026-04")

    # Monthly goal for Groceries: 60000 cents
    goal = MonthlyGoal(
        family_id=family.id,
        category_id=groceries.id,
        year_month="2026-04",
        amount_cents=60000,
    )
    db_session.add(goal)
    await db_session.flush()

    summary = await get_budget_summary(db_session, family_id=family.id, year_month="2026-04")

    category_map = {c.category_name: c for c in summary.categories}

    assert "Groceries" in category_map
    groceries_summary = category_map["Groceries"]
    assert groceries_summary.spent_cents == 15000
    assert groceries_summary.goal_cents == 60000
    assert groceries_summary.status == "green"

    assert "Transport" in category_map
    transport_summary = category_map["Transport"]
    assert transport_summary.spent_cents == 2500
    assert transport_summary.goal_cents is None
    assert transport_summary.status == "none"

    assert summary.total_spent_cents == 17500


@pytest.mark.asyncio
async def test_budget_summary_zero_for_categories_with_no_expenses(db_session: AsyncSession) -> None:
    """get_budget_summary includes active categories with spent_cents=0 when no expenses exist."""
    family, _ = await _make_family(db_session)
    await create_test_category(db_session, family, name="Entertainment")

    summary = await get_budget_summary(db_session, family_id=family.id, year_month="2026-04")

    category_map = {c.category_name: c for c in summary.categories}
    assert "Entertainment" in category_map
    assert category_map["Entertainment"].spent_cents == 0


@pytest.mark.asyncio
async def test_budget_summary_with_no_expenses_total_is_zero(db_session: AsyncSession) -> None:
    """get_budget_summary returns total_spent_cents=0 when there are no expenses."""
    family, _ = await _make_family(db_session)

    summary = await get_budget_summary(db_session, family_id=family.id, year_month="2026-04")

    assert summary.total_spent_cents == 0
    assert summary.year_month == "2026-04"


@pytest.mark.asyncio
async def test_budget_summary_with_goals_computes_status(db_session: AsyncSession) -> None:
    """get_budget_summary computes status correctly based on goal threshold."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family, name="Dining")

    # spent = 85000, goal = 100000 => 85% => "yellow"
    await create_test_expense(db_session, family, user, category, amount_cents=85000, year_month="2026-04")
    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-04",
        amount_cents=100000,
    )
    db_session.add(goal)
    await db_session.flush()

    summary = await get_budget_summary(db_session, family_id=family.id, year_month="2026-04")

    category_map = {c.category_name: c for c in summary.categories}
    assert category_map["Dining"].status == "yellow"


# ---------------------------------------------------------------------------
# _count_category_expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_category_expenses_returns_correct_count(db_session: AsyncSession) -> None:
    """_count_category_expenses returns the correct count after adding expenses."""
    family, user = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    for _ in range(5):
        await create_test_expense(db_session, family, user, category)

    count = await _count_category_expenses(db_session, category.id)

    assert count == 5


@pytest.mark.asyncio
async def test_count_category_expenses_returns_zero_for_empty_category(db_session: AsyncSession) -> None:
    """_count_category_expenses returns 0 when no expenses reference the category."""
    family, _ = await _make_family(db_session)
    category = await create_test_category(db_session, family)

    count = await _count_category_expenses(db_session, category.id)

    assert count == 0
