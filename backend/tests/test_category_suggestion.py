"""Integration tests for the category_suggestion service.

Covers:
- pg_trgm similarity match (similarity > 0.3) returns best-matching category
- pg_trgm skips archived categories
- No match falls back to most-used active category in last 90 days
- Fallback ignores categories used only outside the 90-day window
- Fallback returns highest-count category when multiple candidates exist
- Returns None when family has no categories at all
- Returns None when no similarity match and no recent expenses
"""

from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.receipt import Receipt  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User  # noqa: F401 — registers with Base.metadata
from app.services.category_suggestion import suggest_for_store
from tests.conftest import create_test_category, create_test_expense, create_test_family, create_test_user

# ---------------------------------------------------------------------------
# Local fixture: NullPool engine avoids event-loop conflicts across tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with NullPool engine and per-test transaction rollback."""
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


async def _setup(db: AsyncSession) -> tuple[Family, User]:
    """Create a user and family for testing."""
    user = await create_test_user(db)
    family, _ = await create_test_family(db, user)
    return family, user


def _recent_date(days_ago: int = 10) -> date:
    return date.today() - timedelta(days=days_ago)


def _old_date() -> date:
    return date.today() - timedelta(days=120)


# ---------------------------------------------------------------------------
# pg_trgm similarity tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trgm_returns_similar_category(db_session: AsyncSession) -> None:
    """similarity(name, store_name) > 0.3 returns the matching active category."""
    family, _ = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")
    await create_test_category(db_session, family, name="Transport")

    result = await suggest_for_store(db_session, family.id, "Grocery Store")

    assert result is not None
    assert result.id == groceries.id


@pytest.mark.asyncio
async def test_trgm_skips_archived_category(db_session: AsyncSession) -> None:
    """Archived (is_active=False) categories are excluded from similarity matching."""
    family, _ = await _setup(db_session)
    await create_test_category(db_session, family, name="Groceries", is_active=False)
    dining = await create_test_category(db_session, family, name="Dining")

    result = await suggest_for_store(db_session, family.id, "Grocery Store")

    # Groceries is archived, so only Dining is a candidate — but similarity is low → None or Dining
    # The important check: Groceries (archived) is not returned
    if result is not None:
        assert result.id == dining.id


@pytest.mark.asyncio
async def test_trgm_below_threshold_returns_none_or_fallback(db_session: AsyncSession) -> None:
    """Store names with no similarity match (< 0.3) skip the trgm path."""
    family, _ = await _setup(db_session)
    await create_test_category(db_session, family, name="Groceries")

    # "XYZ123" shares nothing with "Groceries"
    result = await suggest_for_store(db_session, family.id, "XYZ123")

    # No trgm match and no expenses → None
    assert result is None


# ---------------------------------------------------------------------------
# category_hint: the label the receipt extractor picked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hint_matches_where_store_name_cannot(db_session: AsyncSession) -> None:
    """The hint carries the match when the store name shares nothing with any category.

    This is the whole point of the parameter: "Safeway" will never trigram-match
    "Groceries", so without the hint this receipt would fall through to the
    90-day fallback and be flagged needs_edit.
    """
    family, _ = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")
    await create_test_category(db_session, family, name="Transport")

    result = await suggest_for_store(db_session, family.id, "Safeway", category_hint="Groceries")

    assert result is not None
    assert result.id == groceries.id


@pytest.mark.asyncio
async def test_store_name_still_matches_when_hint_misses(db_session: AsyncSession) -> None:
    """A hint that matches nothing does not suppress the store-name trgm path."""
    family, _ = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")

    result = await suggest_for_store(db_session, family.id, "Grocery Store", category_hint="Entertainment")

    assert result is not None
    assert result.id == groceries.id


@pytest.mark.asyncio
async def test_hint_wins_over_store_name(db_session: AsyncSession) -> None:
    """When both terms match different categories, the hint is preferred."""
    family, _ = await _setup(db_session)
    await create_test_category(db_session, family, name="Groceries")
    dining = await create_test_category(db_session, family, name="Dining")

    # "Grocery Store" trgm-matches Groceries, but the extractor saw a restaurant bill.
    result = await suggest_for_store(db_session, family.id, "Grocery Store", category_hint="Dining")

    assert result is not None
    assert result.id == dining.id


@pytest.mark.asyncio
async def test_hint_none_falls_back_as_before(db_session: AsyncSession) -> None:
    """Omitting the hint preserves the original store-name-then-usage behaviour."""
    family, user = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")

    recent = _recent_date()
    await create_test_expense(
        db_session, family, user, groceries, expense_date=recent, year_month=recent.strftime("%Y-%m")
    )

    result = await suggest_for_store(db_session, family.id, "XYZ123", category_hint=None)

    assert result is not None
    assert result.id == groceries.id


# ---------------------------------------------------------------------------
# Fallback: most-used active category in last 90 days
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_returns_most_used_category(db_session: AsyncSession) -> None:
    """When no trgm match, returns the category with the most expenses in last 90 days."""
    family, user = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")
    dining = await create_test_category(db_session, family, name="Dining")

    recent = _recent_date()
    year_month = recent.strftime("%Y-%m")
    await create_test_expense(db_session, family, user, groceries, expense_date=recent, year_month=year_month)
    await create_test_expense(db_session, family, user, groceries, expense_date=recent, year_month=year_month)
    await create_test_expense(db_session, family, user, dining, expense_date=recent, year_month=year_month)

    result = await suggest_for_store(db_session, family.id, "XYZ123")

    assert result is not None
    assert result.id == groceries.id


@pytest.mark.asyncio
async def test_fallback_ignores_expenses_older_than_90_days(db_session: AsyncSession) -> None:
    """Fallback ignores expenses older than 90 days, even if they have the highest count."""
    family, user = await _setup(db_session)
    old_winner = await create_test_category(db_session, family, name="Groceries")
    recent_winner = await create_test_category(db_session, family, name="Dining")

    old = _old_date()
    old_ym = old.strftime("%Y-%m")
    recent = _recent_date()
    recent_ym = recent.strftime("%Y-%m")

    # Old expenses: old_winner used 10 times — outside 90-day window
    for _ in range(10):
        await create_test_expense(db_session, family, user, old_winner, expense_date=old, year_month=old_ym)

    # Recent expenses: recent_winner used 2 times — inside 90-day window
    for _ in range(2):
        await create_test_expense(db_session, family, user, recent_winner, expense_date=recent, year_month=recent_ym)

    result = await suggest_for_store(db_session, family.id, "XYZ123")

    assert result is not None
    assert result.id == recent_winner.id


@pytest.mark.asyncio
async def test_fallback_excludes_archived_categories(db_session: AsyncSession) -> None:
    """Fallback skips categories that are archived (is_active=False)."""
    family, user = await _setup(db_session)
    archived = await create_test_category(db_session, family, name="Groceries", is_active=False)
    active = await create_test_category(db_session, family, name="Dining")

    recent = _recent_date()
    year_month = recent.strftime("%Y-%m")
    # Archived category has more recent expenses
    for _ in range(5):
        await create_test_expense(db_session, family, user, archived, expense_date=recent, year_month=year_month)
    await create_test_expense(db_session, family, user, active, expense_date=recent, year_month=year_month)

    result = await suggest_for_store(db_session, family.id, "XYZ123")

    assert result is not None
    assert result.id == active.id


# ---------------------------------------------------------------------------
# Edge cases: no categories, no recent expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_no_categories(db_session: AsyncSession) -> None:
    """Returns None when the family has no categories at all."""
    family, _ = await _setup(db_session)

    result = await suggest_for_store(db_session, family.id, "Grocery Store")

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_no_match_and_no_recent_expenses(db_session: AsyncSession) -> None:
    """Returns None when no trgm match and no expenses in last 90 days."""
    family, user = await _setup(db_session)
    groceries = await create_test_category(db_session, family, name="Groceries")

    old = _old_date()
    old_ym = old.strftime("%Y-%m")
    await create_test_expense(db_session, family, user, groceries, expense_date=old, year_month=old_ym)

    result = await suggest_for_store(db_session, family.id, "XYZ123")

    assert result is None


@pytest.mark.asyncio
async def test_different_family_categories_not_returned(db_session: AsyncSession) -> None:
    """suggest_for_store only considers categories belonging to the target family."""
    owner = await create_test_user(db_session)
    family1, _ = await create_test_family(db_session, owner)
    family2, _ = await create_test_family(db_session, owner)

    await create_test_category(db_session, family2, name="Groceries")

    result = await suggest_for_store(db_session, family1.id, "Grocery Store")

    assert result is None
