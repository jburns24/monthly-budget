"""Unit tests for the monthly_goal_service module.

Tests exercise all public service functions directly against the database,
verifying correct return values, error handling, and timezone awareness.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

from collections.abc import AsyncGenerator
from datetime import timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.category import Category
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from app.services.monthly_goal_service import (
    copy_goals_from_previous_month,
    get_current_budget_month,
    get_or_check_previous_goals,
    get_previous_month,
    list_goals,
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


async def _insert_category(db: AsyncSession, family: Family, name: str = "Groceries") -> Category:
    """Insert a Category row and return the ORM object."""
    cat = Category(
        family_id=family.id,
        name=name,
        icon=None,
        sort_order=0,
        is_active=True,
    )
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    return cat


async def _insert_goal(
    db: AsyncSession,
    family: Family,
    category: Category,
    year_month: str,
    amount_cents: int = 10000,
) -> MonthlyGoal:
    """Insert a MonthlyGoal row directly and return the ORM object."""
    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month=year_month,
        amount_cents=amount_cents,
        version=1,
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


# ---------------------------------------------------------------------------
# get_previous_month — pure function, no DB needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_previous_month_mid_year() -> None:
    """get_previous_month returns the correct previous month for mid-year months."""
    assert get_previous_month("2026-04") == "2026-03"
    assert get_previous_month("2026-07") == "2026-06"
    assert get_previous_month("2026-12") == "2026-11"


@pytest.mark.asyncio
async def test_get_previous_month_january_wraps_to_previous_year() -> None:
    """get_previous_month wraps January to December of the previous year."""
    assert get_previous_month("2026-01") == "2025-12"
    assert get_previous_month("2000-01") == "1999-12"


@pytest.mark.asyncio
async def test_get_previous_month_february() -> None:
    """get_previous_month handles February correctly."""
    assert get_previous_month("2026-02") == "2026-01"


# ---------------------------------------------------------------------------
# get_current_budget_month — timezone tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_budget_month_la_timezone() -> None:
    """get_current_budget_month returns March when UTC time is April 1 but still March in LA."""
    from datetime import datetime as dt

    # 2026-04-01T03:00:00Z is still 2026-03-31 in America/Los_Angeles (UTC-7 in PDT)
    fixed_utc = dt(2026, 4, 1, 3, 0, 0, tzinfo=timezone.utc)
    with patch("app.services.monthly_goal_service.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_utc
        result = get_current_budget_month("America/Los_Angeles")
    assert result == "2026-03"


@pytest.mark.asyncio
async def test_get_current_budget_month_auckland_timezone() -> None:
    """get_current_budget_month returns April when UTC time is March 31 but April 1 in Auckland."""
    from datetime import datetime as dt

    # 2026-03-31T11:00:00Z is already 2026-04-01 in Pacific/Auckland (UTC+13)
    fixed_utc = dt(2026, 3, 31, 11, 0, 0, tzinfo=timezone.utc)
    with patch("app.services.monthly_goal_service.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_utc
        result = get_current_budget_month("Pacific/Auckland")
    assert result == "2026-04"


@pytest.mark.asyncio
async def test_get_current_budget_month_returns_yyyymm_format() -> None:
    """get_current_budget_month returns a string in YYYY-MM format."""
    result = get_current_budget_month("UTC")
    assert len(result) == 7
    assert result[4] == "-"
    assert result[:4].isdigit()
    assert result[5:].isdigit()


# ---------------------------------------------------------------------------
# get_or_check_previous_goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_check_previous_goals_returns_goals_when_exist(db_session: AsyncSession) -> None:
    """get_or_check_previous_goals returns existing goals with has_previous_goals=False."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Groceries")
    goal = await _insert_goal(db_session, family, cat, "2026-04")

    goals, has_previous = await get_or_check_previous_goals(db_session, family.id, "2026-04")

    assert len(goals) == 1
    assert goals[0].id == goal.id
    assert has_previous is False


@pytest.mark.asyncio
async def test_get_or_check_previous_goals_no_goals_with_previous(db_session: AsyncSession) -> None:
    """get_or_check_previous_goals returns empty list with has_previous_goals=True when prior month has goals."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Dining")
    await _insert_goal(db_session, family, cat, "2026-03")

    goals, has_previous = await get_or_check_previous_goals(db_session, family.id, "2026-04")

    assert goals == []
    assert has_previous is True


@pytest.mark.asyncio
async def test_get_or_check_previous_goals_no_goals_no_previous(db_session: AsyncSession) -> None:
    """get_or_check_previous_goals returns empty list with has_previous_goals=False when no prior goals."""
    family = await _make_family(db_session)

    goals, has_previous = await get_or_check_previous_goals(db_session, family.id, "2026-04")

    assert goals == []
    assert has_previous is False


@pytest.mark.asyncio
async def test_get_or_check_previous_goals_future_months_ignored(db_session: AsyncSession) -> None:
    """get_or_check_previous_goals only looks at months before the requested month."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Bills")
    # Insert a goal for a month AFTER the target — should not count as previous
    await _insert_goal(db_session, family, cat, "2026-05")

    goals, has_previous = await get_or_check_previous_goals(db_session, family.id, "2026-04")

    assert goals == []
    assert has_previous is False


# ---------------------------------------------------------------------------
# copy_goals_from_previous_month
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_copy_goals_from_previous_month_copies_correctly(db_session: AsyncSession) -> None:
    """copy_goals_from_previous_month copies goals from source to target month."""
    family = await _make_family(db_session)
    cat1 = await _insert_category(db_session, family, "Groceries")
    cat2 = await _insert_category(db_session, family, "Dining")
    await _insert_goal(db_session, family, cat1, "2026-03", amount_cents=50000)
    await _insert_goal(db_session, family, cat2, "2026-03", amount_cents=30000)

    copied_count = await copy_goals_from_previous_month(db_session, family.id, "2026-04")

    assert copied_count == 2

    result = await db_session.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family.id,
            MonthlyGoal.year_month == "2026-04",
        )
    )
    new_goals = list(result.scalars().all())
    assert len(new_goals) == 2

    amounts = {g.amount_cents for g in new_goals}
    assert amounts == {50000, 30000}


@pytest.mark.asyncio
async def test_copy_goals_from_previous_month_returns_zero_when_no_source(db_session: AsyncSession) -> None:
    """copy_goals_from_previous_month returns 0 when no previous month has goals."""
    family = await _make_family(db_session)

    copied_count = await copy_goals_from_previous_month(db_session, family.id, "2026-04")

    assert copied_count == 0


@pytest.mark.asyncio
async def test_copy_goals_from_previous_month_finds_most_recent_skipping_gaps(db_session: AsyncSession) -> None:
    """copy_goals_from_previous_month finds the most recent prior month, skipping gaps."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Transport")
    # Goals only in January, no February or March
    await _insert_goal(db_session, family, cat, "2026-01", amount_cents=20000)

    copied_count = await copy_goals_from_previous_month(db_session, family.id, "2026-04")

    assert copied_count == 1

    result = await db_session.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family.id,
            MonthlyGoal.year_month == "2026-04",
        )
    )
    new_goals = list(result.scalars().all())
    assert len(new_goals) == 1
    assert new_goals[0].amount_cents == 20000


@pytest.mark.asyncio
async def test_copy_goals_resets_version_to_one(db_session: AsyncSession) -> None:
    """copy_goals_from_previous_month creates new goals with version=1."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Entertainment")
    source_goal = await _insert_goal(db_session, family, cat, "2026-03")
    # Manually bump version to simulate edits
    source_goal.version = 5
    await db_session.flush()

    await copy_goals_from_previous_month(db_session, family.id, "2026-04")

    result = await db_session.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family.id,
            MonthlyGoal.year_month == "2026-04",
        )
    )
    new_goal = result.scalar_one()
    assert new_goal.version == 1


# ---------------------------------------------------------------------------
# list_goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_goals_returns_goals_when_exist(db_session: AsyncSession) -> None:
    """list_goals returns (goals, False) when goals exist for the month."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Groceries")
    await _insert_goal(db_session, family, cat, "2026-04")

    goals, has_previous = await list_goals(db_session, family.id, "2026-04")

    assert len(goals) == 1
    assert has_previous is False


@pytest.mark.asyncio
async def test_list_goals_returns_has_previous_true_when_prior_goals_exist(db_session: AsyncSession) -> None:
    """list_goals returns ([], True) when no goals for month but prior month has goals."""
    family = await _make_family(db_session)
    cat = await _insert_category(db_session, family, "Dining")
    await _insert_goal(db_session, family, cat, "2026-03")

    goals, has_previous = await list_goals(db_session, family.id, "2026-04")

    assert goals == []
    assert has_previous is True


@pytest.mark.asyncio
async def test_list_goals_returns_has_previous_false_when_no_goals_anywhere(db_session: AsyncSession) -> None:
    """list_goals returns ([], False) when the family has no goals at all."""
    family = await _make_family(db_session)

    goals, has_previous = await list_goals(db_session, family.id, "2026-04")

    assert goals == []
    assert has_previous is False


@pytest.mark.asyncio
async def test_list_goals_isolates_by_family(db_session: AsyncSession) -> None:
    """list_goals does not leak goals from other families."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)
    cat = await _insert_category(db_session, family1, "Bills")
    await _insert_goal(db_session, family1, cat, "2026-03")

    # family2 has no goals and no prior goals
    goals, has_previous = await list_goals(db_session, family2.id, "2026-04")

    assert goals == []
    assert has_previous is False


@pytest.mark.asyncio
async def test_list_goals_multiple_categories(db_session: AsyncSession) -> None:
    """list_goals returns all goals for the month across multiple categories."""
    family = await _make_family(db_session)
    cat1 = await _insert_category(db_session, family, "Groceries")
    cat2 = await _insert_category(db_session, family, "Dining")
    cat3 = await _insert_category(db_session, family, "Transport")
    await _insert_goal(db_session, family, cat1, "2026-04", 50000)
    await _insert_goal(db_session, family, cat2, "2026-04", 30000)
    await _insert_goal(db_session, family, cat3, "2026-04", 20000)

    goals, has_previous = await list_goals(db_session, family.id, "2026-04")

    assert len(goals) == 3
    assert has_previous is False
    amounts = {g.amount_cents for g in goals}
    assert amounts == {50000, 30000, 20000}
