"""Tests for the SQLAlchemy persistence adapter (Postgres tier).

Covers the pieces of ``app/adapters/sqlalchemy/`` that only a real database can
prove: driver error translation, transaction/savepoint semantics, and the
Postgres-tier repository methods (pg_trgm similarity, JOIN + GROUP BY ranking).

The in-memory adapter is tested separately under ``tests/unit/``.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.config import settings
from app.models.category import Category
from app.models.expense import Expense
from app.models.family import Family
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal
from app.models.receipt import Receipt
from app.models.refresh_token_blacklist import RefreshTokenBlacklist
from app.models.user import User
from app.ports.errors import ForeignKeyViolation, UniqueViolation
from tests.conftest import (
    create_test_expense,
    create_test_family,
    create_test_monthly_goal,
    create_test_receipt,
    create_test_user,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback for isolation."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


@pytest.fixture
def uow_factory():
    """Return a factory building a non-owning UoW over a session."""

    def _make(session: AsyncSession) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session, owns_transaction=False)

    return _make


async def _make_family(db: AsyncSession) -> tuple[Family, User]:
    owner = await create_test_user(db)
    family, _ = await create_test_family(db, owner)
    return family, owner


async def _insert(
    db: AsyncSession,
    family: Family,
    name: str,
    *,
    sort_order: int = 0,
    is_active: bool = True,
) -> Category:
    category = Category(family_id=family.id, name=name, sort_order=sort_order, is_active=is_active)
    db.add(category)
    await db.flush()
    return category


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


async def test_flush_translates_duplicate_key_into_unique_violation(db_session, uow_factory) -> None:
    """A duplicate (family_id, name) surfaces as UniqueViolation naming the constraint."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Groceries")
    uow = uow_factory(db_session)

    uow.categories.add(Category(family_id=family.id, name="Groceries"))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_categories_family_name"


async def test_flush_translates_missing_parent_row_into_foreign_key_violation(db_session, uow_factory) -> None:
    """An orphan family_id surfaces as ForeignKeyViolation, not UniqueViolation."""
    uow = uow_factory(db_session)

    uow.categories.add(Category(family_id=uuid.uuid4(), name="Orphan"))

    with pytest.raises(ForeignKeyViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "categories_family_id_fkey"


async def test_flush_re_raises_integrity_errors_it_cannot_classify(db_session, uow_factory) -> None:
    """A NOT NULL violation is not silently relabelled as a port error."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    uow.categories.add(Category(family_id=family.id, name=None))  # type: ignore[arg-type]

    with pytest.raises(IntegrityError):
        await uow.flush()


# ---------------------------------------------------------------------------
# Transaction semantics
# ---------------------------------------------------------------------------


async def test_commit_ends_the_transaction_when_the_uow_owns_it(db_session) -> None:
    """owns_transaction=True means commit() really commits."""
    uow = SqlAlchemyUnitOfWork(db_session, owns_transaction=True)
    assert db_session.in_transaction() is True

    await uow.commit()

    assert db_session.in_transaction() is False


async def test_commit_only_flushes_when_the_uow_does_not_own_the_transaction(db_session, uow_factory) -> None:
    """owns_transaction=False keeps the caller's outer transaction open (test isolation)."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)
    uow.categories.add(Category(family_id=family.id, name="Flushed"))

    await uow.commit()

    assert db_session.in_transaction() is True
    assert await uow.categories.list_names(family.id) == {"Flushed"}


async def test_rollback_discards_writes(db_session, uow_factory) -> None:
    """rollback() throws away everything written since the transaction began."""
    family, _ = await _make_family(db_session)
    family_id = family.id
    uow = uow_factory(db_session)
    uow.categories.add(Category(family_id=family_id, name="Doomed"))
    await uow.flush()

    await uow.rollback()

    assert await uow.categories.list_names(family_id) == set()


async def test_savepoint_rollback_discards_only_writes_inside_it(db_session, uow_factory) -> None:
    """An explicit savepoint rollback keeps writes made before the savepoint."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)
    uow.categories.add(Category(family_id=family.id, name="Keep"))
    await uow.flush()

    async with uow.savepoint() as savepoint:
        uow.categories.add(Category(family_id=family.id, name="Discard"))
        await uow.flush()
        await savepoint.rollback()

    assert await uow.categories.list_names(family.id) == {"Keep"}


async def test_savepoint_rolls_back_on_exception_and_propagates(db_session, uow_factory) -> None:
    """An exception inside the savepoint block rolls it back and is re-raised."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    with pytest.raises(RuntimeError, match="boom"):
        async with uow.savepoint():
            uow.categories.add(Category(family_id=family.id, name="Discard"))
            await uow.flush()
            raise RuntimeError("boom")

    assert await uow.categories.list_names(family.id) == set()


# ---------------------------------------------------------------------------
# CategoryRepository
# ---------------------------------------------------------------------------


async def test_get_in_family_returns_the_category(db_session, uow_factory) -> None:
    """get_in_family finds a category owned by the family."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Dining")
    uow = uow_factory(db_session)

    found = await uow.categories.get_in_family(category.id, family.id)

    assert found is not None
    assert found.id == category.id


async def test_get_in_family_returns_none_for_another_familys_category(db_session, uow_factory) -> None:
    """get_in_family scopes by family_id, so cross-family reads return None."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    category = await _insert(db_session, family_one, "Private")
    uow = uow_factory(db_session)

    assert await uow.categories.get_in_family(category.id, family_two.id) is None


async def test_list_active_excludes_archived_and_sorts_by_sort_order_then_name(db_session, uow_factory) -> None:
    """list_active returns active categories ordered by (sort_order, name)."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Zebra", sort_order=1)
    await _insert(db_session, family, "Apple", sort_order=2)
    await _insert(db_session, family, "Mango", sort_order=1)
    await _insert(db_session, family, "Archived", sort_order=0, is_active=False)
    uow = uow_factory(db_session)

    names = [c.name for c in await uow.categories.list_active(family.id)]

    assert names == ["Mango", "Zebra", "Apple"]


async def test_list_names_includes_archived_categories(db_session, uow_factory) -> None:
    """list_names backs the seeding idempotency check, so it must see archived names too."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Active")
    await _insert(db_session, family, "Archived", is_active=False)
    uow = uow_factory(db_session)

    assert await uow.categories.list_names(family.id) == {"Active", "Archived"}


async def test_first_active_returns_the_lowest_sorted_active_category(db_session, uow_factory) -> None:
    """first_active picks by (sort_order, name) and ignores archived rows."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Later", sort_order=5)
    await _insert(db_session, family, "Earliest", sort_order=1)
    await _insert(db_session, family, "Archived", sort_order=0, is_active=False)
    uow = uow_factory(db_session)

    first = await uow.categories.first_active(family.id)

    assert first is not None
    assert first.name == "Earliest"


async def test_first_active_returns_none_without_active_categories(db_session, uow_factory) -> None:
    """first_active returns None when the family has nothing active."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    assert await uow.categories.first_active(family.id) is None


async def test_add_all_inserts_every_category(db_session, uow_factory) -> None:
    """add_all stages a whole batch for the next flush."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    uow.categories.add_all(
        [
            Category(family_id=family.id, name="One", sort_order=0),
            Category(family_id=family.id, name="Two", sort_order=1),
        ]
    )
    await uow.flush()

    assert await uow.categories.list_names(family.id) == {"One", "Two"}


async def test_delete_removes_the_row(db_session, uow_factory) -> None:
    """delete followed by flush removes the category."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Gone")
    uow = uow_factory(db_session)

    await uow.categories.delete(category)
    await uow.flush()

    assert await uow.categories.list_names(family.id) == set()


# ---------------------------------------------------------------------------
# CategoryRepository — Postgres-tier methods
# ---------------------------------------------------------------------------


async def test_find_similar_active_matches_on_trigram_similarity(db_session, uow_factory) -> None:
    """find_similar_active uses pg_trgm so near-miss spellings still match."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Groceries")
    uow = uow_factory(db_session)

    match = await uow.categories.find_similar_active(family.id, "Grocery", 0.3)

    assert match is not None
    assert match.name == "Groceries"


async def test_find_similar_active_returns_none_below_the_threshold(db_session, uow_factory) -> None:
    """An unrelated term does not match."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Groceries")
    uow = uow_factory(db_session)

    assert await uow.categories.find_similar_active(family.id, "Safeway", 0.3) is None


async def test_find_similar_active_ignores_archived_categories(db_session, uow_factory) -> None:
    """Archived categories are never suggested."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Groceries", is_active=False)
    uow = uow_factory(db_session)

    assert await uow.categories.find_similar_active(family.id, "Groceries", 0.3) is None


async def test_most_used_since_returns_the_category_with_the_most_recent_expenses(db_session, uow_factory) -> None:
    """most_used_since ranks active categories by expense count since the cutoff."""
    family, owner = await _make_family(db_session)
    popular = await _insert(db_session, family, "Popular")
    rare = await _insert(db_session, family, "Rare")
    recent = date.today() - timedelta(days=5)
    for _ in range(3):
        await create_test_expense(db_session, family, owner, popular, expense_date=recent)
    await create_test_expense(db_session, family, owner, rare, expense_date=recent)
    uow = uow_factory(db_session)

    winner = await uow.categories.most_used_since(family.id, date.today() - timedelta(days=90))

    assert winner is not None
    assert winner.name == "Popular"


async def test_most_used_since_ignores_expenses_older_than_the_cutoff(db_session, uow_factory) -> None:
    """Expenses before the cutoff do not count."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Stale")
    await create_test_expense(db_session, family, owner, category, expense_date=date.today() - timedelta(days=200))
    uow = uow_factory(db_session)

    assert await uow.categories.most_used_since(family.id, date.today() - timedelta(days=90)) is None


# ---------------------------------------------------------------------------
# ExpenseRepository
# ---------------------------------------------------------------------------


async def test_expense_get_in_family_returns_the_expense(db_session, uow_factory) -> None:
    """get_in_family finds an expense owned by the family, with no relationships loaded."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    expense = await create_test_expense(db_session, family, owner, category)
    uow = uow_factory(db_session)

    found = await uow.expenses.get_in_family(expense.id, family.id)

    assert found is not None
    assert found.id == expense.id


async def test_expense_get_in_family_returns_none_for_another_familys_expense(db_session, uow_factory) -> None:
    """get_in_family scopes by family_id."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    category = await _insert(db_session, family_one, "Groceries")
    expense = await create_test_expense(db_session, family_one, owner, category)
    uow = uow_factory(db_session)

    assert await uow.expenses.get_in_family(expense.id, family_two.id) is None


async def test_expense_get_in_family_with_details_eager_loads_category_user_and_receipt(
    db_session, uow_factory
) -> None:
    """get_in_family_with_details is what ExpenseResponse.model_validate needs (risk (a))."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    expense = await create_test_expense(db_session, family, owner, category)
    uow = uow_factory(db_session)

    found = await uow.expenses.get_in_family_with_details(expense.id, family.id)

    assert found is not None
    assert found.category is not None
    assert found.category.id == category.id
    assert found.user is not None
    assert found.user.id == owner.id
    assert found.receipt is None
    assert found.receipt_status is None


async def test_expense_get_in_family_with_details_returns_none_for_an_unknown_id(db_session, uow_factory) -> None:
    """A missing id is None, not an error."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    assert await uow.expenses.get_in_family_with_details(uuid.uuid4(), family.id) is None


async def test_expense_list_for_month_is_scoped_to_family_and_month(db_session, uow_factory) -> None:
    """list_for_month filters on both family_id and year_month."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    await create_test_expense(db_session, family, owner, category, year_month="2026-04")
    await create_test_expense(db_session, family, owner, category, year_month="2026-03")
    uow = uow_factory(db_session)

    results = await uow.expenses.list_for_month(family.id, "2026-04", None, 50, 0)

    assert len(results) == 1


async def test_expense_list_for_month_filters_by_category(db_session, uow_factory) -> None:
    """list_for_month optionally filters by category_id."""
    family, owner = await _make_family(db_session)
    groceries = await _insert(db_session, family, "Groceries")
    transport = await _insert(db_session, family, "Transport")
    await create_test_expense(db_session, family, owner, groceries, year_month="2026-04")
    await create_test_expense(db_session, family, owner, transport, year_month="2026-04")
    uow = uow_factory(db_session)

    results = await uow.expenses.list_for_month(family.id, "2026-04", groceries.id, 50, 0)

    assert len(results) == 1
    assert results[0].category_id == groceries.id


async def test_expense_list_for_month_orders_newest_first_and_eager_loads(db_session, uow_factory) -> None:
    """list_for_month orders by (expense_date DESC, created_at DESC) and eager-loads relationships."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    early = await create_test_expense(
        db_session, family, owner, category, year_month="2026-04", expense_date=date(2026, 4, 1)
    )
    late = await create_test_expense(
        db_session, family, owner, category, year_month="2026-04", expense_date=date(2026, 4, 15)
    )
    uow = uow_factory(db_session)

    results = await uow.expenses.list_for_month(family.id, "2026-04", None, 50, 0)

    assert [e.id for e in results] == [late.id, early.id]
    assert all(e.category is not None and e.user is not None for e in results)


async def test_expense_list_for_month_paginates_with_limit_and_offset(db_session, uow_factory) -> None:
    """limit/offset back the API's page/per_page."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    for day in range(1, 6):
        await create_test_expense(
            db_session, family, owner, category, year_month="2026-04", expense_date=date(2026, 4, day)
        )
    uow = uow_factory(db_session)

    page = await uow.expenses.list_for_month(family.id, "2026-04", None, 2, 2)

    assert len(page) == 2


async def test_expense_count_for_month_matches_list_for_month(db_session, uow_factory) -> None:
    """count_for_month backs pagination's total_count."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    for _ in range(3):
        await create_test_expense(db_session, family, owner, category, year_month="2026-04")
    uow = uow_factory(db_session)

    assert await uow.expenses.count_for_month(family.id, "2026-04", None) == 3


async def test_expense_count_for_month_filters_by_category(db_session, uow_factory) -> None:
    """count_for_month optionally filters by category_id."""
    family, owner = await _make_family(db_session)
    groceries = await _insert(db_session, family, "Groceries")
    transport = await _insert(db_session, family, "Transport")
    await create_test_expense(db_session, family, owner, groceries, year_month="2026-04")
    await create_test_expense(db_session, family, owner, transport, year_month="2026-04")
    await create_test_expense(db_session, family, owner, transport, year_month="2026-04")
    uow = uow_factory(db_session)

    assert await uow.expenses.count_for_month(family.id, "2026-04", transport.id) == 2


async def test_expense_add_then_flush_persists_it(db_session, uow_factory) -> None:
    """add() stages a new expense until flush()."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    uow = uow_factory(db_session)
    expense = Expense(
        family_id=family.id,
        user_id=owner.id,
        category_id=category.id,
        amount_cents=1000,
        description="Adapter test",
        expense_date=date(2026, 4, 1),
        year_month="2026-04",
    )

    uow.expenses.add(expense)
    await uow.flush()

    assert await uow.expenses.count_for_month(family.id, "2026-04", None) == 1


async def test_expense_delete_removes_the_row(db_session, uow_factory) -> None:
    """delete followed by flush removes the expense."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    expense = await create_test_expense(db_session, family, owner, category)
    uow = uow_factory(db_session)

    await uow.expenses.delete(expense)
    await uow.flush()

    assert await uow.expenses.get_in_family(expense.id, family.id) is None


async def test_count_by_category_counts_referencing_expenses(db_session, uow_factory) -> None:
    """count_by_category is the cross-aggregate read behind archive-vs-delete."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Counted")
    for _ in range(5):
        await create_test_expense(db_session, family, owner, category)
    uow = uow_factory(db_session)

    assert await uow.expenses.count_by_category(category.id) == 5


async def test_count_by_category_is_scoped_to_the_category_not_the_family(db_session, uow_factory) -> None:
    """count_by_category is keyed on the category, not the family, and is 0 rather than None."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    category_one = await _insert(db_session, family_one, "One")
    category_two = await _insert(db_session, family_two, "Two")
    await create_test_expense(db_session, family_one, owner, category_one)
    uow = uow_factory(db_session)

    assert await uow.expenses.count_by_category(category_one.id) == 1
    assert await uow.expenses.count_by_category(category_two.id) == 0


# ---------------------------------------------------------------------------
# expire_on_commit / server defaults
# ---------------------------------------------------------------------------


async def test_flush_populates_server_side_created_at(db_session, uow_factory) -> None:
    """created_at comes from server_default, which the memory store must emulate."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)
    category = Category(family_id=family.id, name="Defaulted")

    uow.categories.add(category)
    await uow.flush()
    await db_session.refresh(category)

    assert isinstance(category.created_at, datetime)
    assert category.created_at.tzinfo is not None
    assert category.created_at < datetime.now(tz=timezone.utc) + timedelta(minutes=5)


# ---------------------------------------------------------------------------
# MonthlyGoalRepository
# ---------------------------------------------------------------------------


async def test_goal_get_in_family_returns_the_goal(db_session, uow_factory) -> None:
    """get_in_family finds a goal owned by the family."""
    family, owner = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    goal = await create_test_monthly_goal(db_session, family, category, "2026-04")
    uow = uow_factory(db_session)

    found = await uow.goals.get_in_family(goal.id, family.id)

    assert found is not None
    assert found.id == goal.id


async def test_goal_get_in_family_returns_none_for_another_familys_goal(db_session, uow_factory) -> None:
    """get_in_family scopes by family_id, so cross-family reads return None."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    category = await _insert(db_session, family_one, "Groceries")
    goal = await create_test_monthly_goal(db_session, family_one, category, "2026-04")
    uow = uow_factory(db_session)

    assert await uow.goals.get_in_family(goal.id, family_two.id) is None


async def test_goal_get_in_family_returns_none_for_an_unknown_id(db_session, uow_factory) -> None:
    """A missing id is None, not an error."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    assert await uow.goals.get_in_family(uuid.uuid4(), family.id) is None


async def test_goal_list_for_month_is_scoped_to_family_and_month(db_session, uow_factory) -> None:
    """list_for_month filters on both family_id and year_month."""
    family, _ = await _make_family(db_session)
    cat1 = await _insert(db_session, family, "Groceries")
    cat2 = await _insert(db_session, family, "Dining")
    await create_test_monthly_goal(db_session, family, cat1, "2026-04")
    await create_test_monthly_goal(db_session, family, cat2, "2026-03")
    uow = uow_factory(db_session)

    goals = await uow.goals.list_for_month(family.id, "2026-04")

    assert len(goals) == 1
    assert goals[0].category_id == cat1.id


async def test_goal_latest_month_before_finds_the_most_recent_prior_month(db_session, uow_factory) -> None:
    """latest_month_before is a string-comparison MAX, skipping gaps."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Transport")
    await create_test_monthly_goal(db_session, family, category, "2026-01")
    uow = uow_factory(db_session)

    result = await uow.goals.latest_month_before(family.id, "2026-04")

    assert result == "2026-01"


async def test_goal_latest_month_before_ignores_months_on_or_after_the_target(db_session, uow_factory) -> None:
    """Only months strictly before year_month count."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Transport")
    await create_test_monthly_goal(db_session, family, category, "2026-04")
    uow = uow_factory(db_session)

    assert await uow.goals.latest_month_before(family.id, "2026-04") is None


async def test_goal_latest_month_before_returns_none_without_prior_goals(db_session, uow_factory) -> None:
    """No goals at all means None, not an error."""
    family, _ = await _make_family(db_session)
    uow = uow_factory(db_session)

    assert await uow.goals.latest_month_before(family.id, "2026-04") is None


async def test_goal_add_all_inserts_every_goal(db_session, uow_factory) -> None:
    """add_all stages a whole batch for the next flush."""
    family, _ = await _make_family(db_session)
    cat1 = await _insert(db_session, family, "Groceries")
    cat2 = await _insert(db_session, family, "Dining")
    uow = uow_factory(db_session)

    uow.goals.add_all(
        [
            MonthlyGoal(family_id=family.id, category_id=cat1.id, year_month="2026-04", amount_cents=1000, version=1),
            MonthlyGoal(family_id=family.id, category_id=cat2.id, year_month="2026-04", amount_cents=2000, version=1),
        ]
    )
    await uow.flush()

    assert len(await uow.goals.list_for_month(family.id, "2026-04")) == 2


async def test_goal_delete_removes_the_row(db_session, uow_factory) -> None:
    """delete followed by flush removes the goal."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    goal = await create_test_monthly_goal(db_session, family, category, "2026-04")
    uow = uow_factory(db_session)

    await uow.goals.delete(goal)
    await uow.flush()

    assert await uow.goals.list_for_month(family.id, "2026-04") == []


async def test_flush_translates_duplicate_goal_into_unique_violation(db_session, uow_factory) -> None:
    """A duplicate (family_id, category_id, year_month) surfaces as UniqueViolation."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    await create_test_monthly_goal(db_session, family, category, "2026-04")
    uow = uow_factory(db_session)

    uow.goals.add(
        MonthlyGoal(family_id=family.id, category_id=category.id, year_month="2026-04", amount_cents=500, version=1)
    )

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_monthly_goals_family_category_month"


async def test_goal_flush_populates_server_side_created_at(db_session, uow_factory) -> None:
    """created_at comes from server_default, which the memory store must emulate."""
    family, _ = await _make_family(db_session)
    category = await _insert(db_session, family, "Groceries")
    uow = uow_factory(db_session)
    goal = MonthlyGoal(family_id=family.id, category_id=category.id, year_month="2026-04", amount_cents=1000, version=1)

    uow.goals.add(goal)
    await uow.flush()

    assert isinstance(goal.created_at, datetime)
    assert goal.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


async def test_user_get_returns_the_user(db_session, uow_factory) -> None:
    """get finds a user by primary key."""
    user = await create_test_user(db_session)
    uow = uow_factory(db_session)

    found = await uow.users.get(user.id)

    assert found is not None
    assert found.id == user.id


async def test_user_get_returns_none_for_an_unknown_id(db_session, uow_factory) -> None:
    """A missing id is None, not an error."""
    uow = uow_factory(db_session)

    assert await uow.users.get(uuid.uuid4()) is None


async def test_user_get_by_google_id_finds_the_user(db_session, uow_factory) -> None:
    """get_by_google_id backs the OAuth login upsert."""
    user = await create_test_user(db_session, google_id="google_unique_123")
    uow = uow_factory(db_session)

    found = await uow.users.get_by_google_id("google_unique_123")

    assert found is not None
    assert found.id == user.id


async def test_user_get_by_email_finds_the_user(db_session, uow_factory) -> None:
    """get_by_email backs the invite-by-email lookup."""
    user = await create_test_user(db_session, email="alice-adapter@example.com")
    uow = uow_factory(db_session)

    found = await uow.users.get_by_email("alice-adapter@example.com")

    assert found is not None
    assert found.id == user.id


async def test_user_add_stages_a_new_user_until_flush(db_session, uow_factory) -> None:
    """add() plus flush() persists a brand-new user."""
    uow = uow_factory(db_session)
    user = User(google_id="google_new", email="new@example.com", display_name="New User")

    uow.users.add(user)
    await uow.flush()

    assert await uow.users.get_by_google_id("google_new") is not None


async def test_flush_translates_duplicate_google_id_into_unique_violation(db_session, uow_factory) -> None:
    """A duplicate google_id surfaces as UniqueViolation."""
    await create_test_user(db_session, google_id="google_dup")
    uow = uow_factory(db_session)

    uow.users.add(User(google_id="google_dup", email="other@example.com", display_name="Dup"))

    with pytest.raises(UniqueViolation):
        await uow.flush()


# ---------------------------------------------------------------------------
# FamilyMemberRepository
# ---------------------------------------------------------------------------


async def test_member_get_for_user_in_family_returns_the_member(db_session, uow_factory) -> None:
    """get_for_user_in_family finds the membership scoped to both ids."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    found = await uow.members.get_for_user_in_family(family.id, owner.id)

    assert found is not None
    assert found.role == "admin"


async def test_member_get_for_user_in_family_returns_none_for_a_different_family(db_session, uow_factory) -> None:
    """The lookup is scoped by family_id, not just user_id."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    assert await uow.members.get_for_user_in_family(uuid.uuid4(), owner.id) is None


async def test_member_get_any_for_user_returns_the_membership(db_session, uow_factory) -> None:
    """get_any_for_user finds the single family a user belongs to."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    found = await uow.members.get_any_for_user(owner.id)

    assert found is not None
    assert found.family_id == family.id


async def test_member_get_with_family_eager_loads_family(db_session, uow_factory) -> None:
    """get_with_family replaces ``db.refresh(membership, ['family'])`` in users.py."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    found = await uow.members.get_with_family(owner.id)

    assert found is not None
    assert found.family.name == family.name


async def test_member_get_with_user_eager_loads_user(db_session, uow_factory) -> None:
    """get_with_user replaces ``db.refresh(member, ['user'])`` in family.py."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    found = await uow.members.get_with_user(family.id, owner.id)

    assert found is not None
    assert found.user.id == owner.id


async def test_member_count_admins_counts_only_admins(db_session, uow_factory) -> None:
    """count_admins backs the "cannot remove/demote the last admin" guards."""
    family, owner = await _make_family(db_session)
    second_user = await create_test_user(db_session)
    db_session.add(FamilyMember(family_id=family.id, user_id=second_user.id, role="member"))
    await db_session.flush()
    uow = uow_factory(db_session)

    assert await uow.members.count_admins(family.id) == 1


async def test_member_add_and_delete(db_session, uow_factory) -> None:
    """add() stages a new membership; delete() removes one on flush."""
    family, owner = await _make_family(db_session)
    second_user = await create_test_user(db_session)
    uow = uow_factory(db_session)
    member = FamilyMember(family_id=family.id, user_id=second_user.id, role="member")

    uow.members.add(member)
    await uow.flush()
    assert await uow.members.get_for_user_in_family(family.id, second_user.id) is not None

    await uow.members.delete(member)
    await uow.flush()
    assert await uow.members.get_for_user_in_family(family.id, second_user.id) is None


async def test_flush_translates_duplicate_family_member_into_unique_violation(db_session, uow_factory) -> None:
    """A duplicate (family_id, user_id) surfaces as UniqueViolation."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)

    uow.members.add(FamilyMember(family_id=family.id, user_id=owner.id, role="member"))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_family_members_family_user"


# ---------------------------------------------------------------------------
# ReceiptRepository
# ---------------------------------------------------------------------------


async def test_receipt_get_in_family_returns_the_receipt(db_session, uow_factory) -> None:
    """get_in_family finds a receipt owned by the family."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner)
    uow = uow_factory(db_session)

    found = await uow.receipts.get_in_family(receipt.id, family.id)

    assert found is not None
    assert found.id == receipt.id


async def test_receipt_get_in_family_returns_none_for_another_familys_receipt(db_session, uow_factory) -> None:
    """get_in_family scopes by family_id, so cross-family reads return None."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    receipt = await create_test_receipt(db_session, family_one, owner)
    uow = uow_factory(db_session)

    assert await uow.receipts.get_in_family(receipt.id, family_two.id) is None


async def test_list_filtered_orders_by_created_at_descending(db_session, uow_factory) -> None:
    """list_filtered returns the family's receipts, newest created_at first."""
    family, owner = await _make_family(db_session)
    now = datetime.now(tz=timezone.utc)
    oldest = await create_test_receipt(db_session, family, owner, created_at=now - timedelta(minutes=10))
    middle = await create_test_receipt(db_session, family, owner, created_at=now - timedelta(minutes=5))
    newest = await create_test_receipt(db_session, family, owner, created_at=now)
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, None, None, None, 50, 0)

    assert [r.id for r in results] == [newest.id, middle.id, oldest.id]


async def test_list_filtered_by_status_in_isolation(db_session, uow_factory) -> None:
    """A status filter returns only receipts in that status."""
    family, owner = await _make_family(db_session)
    completed = await create_test_receipt(db_session, family, owner, status="completed")
    await create_test_receipt(db_session, family, owner, status="failed")
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, "completed", None, None, None, 50, 0)

    assert [r.id for r in results] == [completed.id]


async def test_list_filtered_by_uploaded_by_in_isolation(db_session, uow_factory) -> None:
    """An uploaded_by filter returns only that uploader's receipts."""
    family, owner = await _make_family(db_session)
    other = await create_test_user(db_session)
    mine = await create_test_receipt(db_session, family, owner)
    await create_test_receipt(db_session, family, other)
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, owner.id, None, None, 50, 0)

    assert [r.id for r in results] == [mine.id]


async def test_list_filtered_by_date_from_in_isolation(db_session, uow_factory) -> None:
    """A date_from filter excludes receipts parsed before that date."""
    family, owner = await _make_family(db_session)
    recent = await create_test_receipt(db_session, family, owner, parsed_date=date(2026, 4, 10))
    await create_test_receipt(db_session, family, owner, parsed_date=date(2026, 3, 1))
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, None, date(2026, 4, 1), None, 50, 0)

    assert [r.id for r in results] == [recent.id]


async def test_list_filtered_by_date_to_in_isolation(db_session, uow_factory) -> None:
    """A date_to filter excludes receipts parsed after that date."""
    family, owner = await _make_family(db_session)
    early = await create_test_receipt(db_session, family, owner, parsed_date=date(2026, 3, 1))
    await create_test_receipt(db_session, family, owner, parsed_date=date(2026, 4, 10))
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, None, None, date(2026, 3, 31), 50, 0)

    assert [r.id for r in results] == [early.id]


async def test_list_filtered_excludes_null_parsed_date_when_date_from_is_set(db_session, uow_factory) -> None:
    """A NULL parsed_date (still processing, or failed) never satisfies a date_from filter.

    SQL comparisons against NULL evaluate to unknown, not true, so
    ``parsed_date >= date_from`` silently drops a still-processing receipt.
    This is the behaviour the in-memory fake has to mirror, so pinning it
    against real SQL is the point.
    """
    family, owner = await _make_family(db_session)
    await create_test_receipt(db_session, family, owner, parsed_date=None)
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, None, date(2020, 1, 1), None, 50, 0)

    assert results == []


async def test_list_filtered_excludes_null_parsed_date_when_date_to_is_set(db_session, uow_factory) -> None:
    """A NULL parsed_date also fails ``parsed_date <= date_to``, for the same reason."""
    family, owner = await _make_family(db_session)
    await create_test_receipt(db_session, family, owner, parsed_date=None)
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, None, None, None, date(2030, 1, 1), 50, 0)

    assert results == []


async def test_list_filtered_combines_status_and_uploaded_by(db_session, uow_factory) -> None:
    """Filters combine with AND, not OR."""
    family, owner = await _make_family(db_session)
    other = await create_test_user(db_session)
    match = await create_test_receipt(db_session, family, owner, status="completed")
    await create_test_receipt(db_session, family, owner, status="failed")
    await create_test_receipt(db_session, family, other, status="completed")
    uow = uow_factory(db_session)

    results = await uow.receipts.list_filtered(family.id, "completed", owner.id, None, None, 50, 0)

    assert [r.id for r in results] == [match.id]


async def test_list_filtered_paginates_with_limit_and_offset(db_session, uow_factory) -> None:
    """limit/offset back the API's page/per_page, honoring created_at DESC order."""
    family, owner = await _make_family(db_session)
    now = datetime.now(tz=timezone.utc)
    receipts = [
        await create_test_receipt(db_session, family, owner, created_at=now - timedelta(minutes=i)) for i in range(5)
    ]
    uow = uow_factory(db_session)

    page = await uow.receipts.list_filtered(family.id, None, None, None, None, 2, 2)

    assert [r.id for r in page] == [receipts[2].id, receipts[3].id]


async def test_list_filtered_is_scoped_to_the_family(db_session, uow_factory) -> None:
    """Receipts from another family never appear."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    await create_test_receipt(db_session, family_two, owner)
    uow = uow_factory(db_session)

    assert await uow.receipts.list_filtered(family_one.id, None, None, None, None, 50, 0) == []


async def test_get_status_returns_the_status(db_session, uow_factory) -> None:
    """get_status reads the persisted column directly, not a possibly-stale instance."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner, status="completed")
    uow = uow_factory(db_session)

    assert await uow.receipts.get_status(receipt.id) == "completed"


async def test_get_status_returns_none_for_an_unknown_id(db_session, uow_factory) -> None:
    """A missing id is None, not an error."""
    uow = uow_factory(db_session)

    assert await uow.receipts.get_status(uuid.uuid4()) is None


async def test_receipt_add_then_flush_assigns_id_and_server_side_created_at(db_session, uow_factory) -> None:
    """add() stages a new receipt; flush() assigns its id and created_at server default."""
    family, owner = await _make_family(db_session)
    uow = uow_factory(db_session)
    receipt = Receipt(family_id=family.id, uploaded_by=owner.id, status="processing")

    uow.receipts.add(receipt)
    await uow.flush()
    await db_session.refresh(receipt)

    assert receipt.id is not None
    assert isinstance(receipt.created_at, datetime)
    assert receipt.created_at.tzinfo is not None


async def test_receipt_delete_removes_the_row(db_session, uow_factory) -> None:
    """delete followed by flush removes the receipt."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner)
    uow = uow_factory(db_session)

    await uow.receipts.delete(receipt)
    await uow.flush()

    assert await uow.receipts.get_in_family(receipt.id, family.id) is None


# claim_for_retry — the concurrency guarantee (two connections racing the same
# failed row, exactly one winning) is NOT retested here: it needs two real
# database connections to exercise Postgres's row locking, which this single
# session, single-connection db_session fixture cannot provide. That scenario
# is already covered by tests/test_receipts_api.py::test_retry_concurrent_only_one_succeeds,
# which has the two-connection machinery for it.


async def test_claim_for_retry_moves_a_failed_receipt_to_processing(db_session, uow_factory) -> None:
    """A failed receipt is claimed: status flips to processing and error_message is cleared."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner, status="failed", error_message="Claude timed out")
    uow = uow_factory(db_session)

    claimed = await uow.receipts.claim_for_retry(receipt.id)

    assert claimed is True
    await db_session.refresh(receipt)
    assert receipt.status == "processing"
    assert receipt.error_message is None


async def test_claim_for_retry_does_not_touch_a_completed_receipt(db_session, uow_factory) -> None:
    """A completed receipt cannot be claimed; nothing about it changes."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner, status="completed")
    uow = uow_factory(db_session)

    claimed = await uow.receipts.claim_for_retry(receipt.id)

    assert claimed is False
    await db_session.refresh(receipt)
    assert receipt.status == "completed"


async def test_claim_for_retry_does_not_touch_a_processing_receipt(db_session, uow_factory) -> None:
    """A receipt already processing cannot be claimed again."""
    family, owner = await _make_family(db_session)
    receipt = await create_test_receipt(db_session, family, owner, status="processing")
    uow = uow_factory(db_session)

    claimed = await uow.receipts.claim_for_retry(receipt.id)

    assert claimed is False
    await db_session.refresh(receipt)
    assert receipt.status == "processing"


async def test_claim_for_retry_returns_false_for_an_unknown_id(db_session, uow_factory) -> None:
    """A missing id claims nothing and does not raise."""
    uow = uow_factory(db_session)

    assert await uow.receipts.claim_for_retry(uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# RefreshTokenRepository
# ---------------------------------------------------------------------------


def _blacklist_entry(user: User, jti: str, *, expires_in: timedelta = timedelta(days=7)) -> RefreshTokenBlacklist:
    now = datetime.now(tz=timezone.utc)
    return RefreshTokenBlacklist(jti=jti, user_id=user.id, expires_at=now + expires_in, created_at=now)


async def test_token_is_blacklisted_is_false_for_an_unknown_jti(db_session, uow_factory) -> None:
    """A jti nobody revoked is not blacklisted."""
    uow = uow_factory(db_session)

    assert await uow.tokens.is_blacklisted(uuid.uuid4().hex) is False


async def test_token_add_then_flush_makes_the_jti_blacklisted(db_session, uow_factory) -> None:
    """add() plus flush() is what /api/auth/logout does; /refresh must then reject it."""
    user = await create_test_user(db_session)
    uow = uow_factory(db_session)
    jti = uuid.uuid4().hex

    uow.tokens.add(_blacklist_entry(user, jti))
    await uow.flush()

    assert await uow.tokens.is_blacklisted(jti) is True


async def test_token_add_assigns_an_id_at_flush(db_session, uow_factory) -> None:
    """id is a Python-side uuid4 default, filled in on flush."""
    user = await create_test_user(db_session)
    uow = uow_factory(db_session)
    entry = _blacklist_entry(user, uuid.uuid4().hex)

    uow.tokens.add(entry)
    await uow.flush()

    assert isinstance(entry.id, uuid.UUID)


async def test_token_is_blacklisted_ignores_expiry(db_session, uow_factory) -> None:
    """An expired row still blocks the jti — the inline query filtered on jti alone."""
    user = await create_test_user(db_session)
    uow = uow_factory(db_session)
    jti = uuid.uuid4().hex

    uow.tokens.add(_blacklist_entry(user, jti, expires_in=timedelta(days=-30)))
    await uow.flush()

    assert await uow.tokens.is_blacklisted(jti) is True


async def test_flush_translates_duplicate_jti_into_unique_violation(db_session, uow_factory) -> None:
    """``jti`` is unique; a second revocation of the same token is a UniqueViolation."""
    user = await create_test_user(db_session)
    uow = uow_factory(db_session)
    jti = uuid.uuid4().hex

    uow.tokens.add(_blacklist_entry(user, jti))
    await uow.flush()
    uow.tokens.add(_blacklist_entry(user, jti))

    with pytest.raises(UniqueViolation):
        await uow.flush()


async def test_token_add_for_an_unknown_user_is_a_foreign_key_violation(db_session, uow_factory) -> None:
    """user_id is a FK to users.id, so an orphan revocation is rejected."""
    uow = uow_factory(db_session)
    now = datetime.now(tz=timezone.utc)

    uow.tokens.add(
        RefreshTokenBlacklist(
            jti=uuid.uuid4().hex,
            user_id=uuid.uuid4(),
            expires_at=now + timedelta(days=7),
            created_at=now,
        )
    )

    with pytest.raises(ForeignKeyViolation):
        await uow.flush()


# ---------------------------------------------------------------------------
# BudgetQuery — Postgres tier, no fake (5-way aggregate with a subquery)
# ---------------------------------------------------------------------------


async def test_category_spend_and_goals_aggregates_spend_and_goal_per_category(db_session, uow_factory) -> None:
    """category_spend_and_goals sums expenses and attaches the month's goal per category."""
    family, owner = await _make_family(db_session)
    groceries = await _insert(db_session, family, "Groceries")
    transport = await _insert(db_session, family, "Transport")
    for amount in (5000, 5000, 5000):
        await create_test_expense(db_session, family, owner, groceries, amount_cents=amount, year_month="2026-04")
    await create_test_expense(db_session, family, owner, transport, amount_cents=2500, year_month="2026-04")
    await create_test_monthly_goal(db_session, family, groceries, year_month="2026-04", amount_cents=60000)
    uow = uow_factory(db_session)

    rows = await uow.budget.category_spend_and_goals(family.id, "2026-04")

    by_name = {r.category_name: r for r in rows}
    assert by_name["Groceries"].spent_cents == 15000
    assert by_name["Groceries"].goal_cents == 60000
    assert by_name["Transport"].spent_cents == 2500
    assert by_name["Transport"].goal_cents is None


async def test_category_spend_and_goals_includes_categories_with_no_expenses(db_session, uow_factory) -> None:
    """An active category with nothing spent still gets a row, with spent_cents=0."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Entertainment")
    uow = uow_factory(db_session)

    rows = await uow.budget.category_spend_and_goals(family.id, "2026-04")

    assert len(rows) == 1
    assert rows[0].spent_cents == 0
    assert rows[0].goal_cents is None


async def test_category_spend_and_goals_excludes_archived_categories(db_session, uow_factory) -> None:
    """Archived categories are never part of the budget summary."""
    family, _ = await _make_family(db_session)
    await _insert(db_session, family, "Archived", is_active=False)
    uow = uow_factory(db_session)

    assert await uow.budget.category_spend_and_goals(family.id, "2026-04") == []


async def test_category_spend_and_goals_is_scoped_to_the_family_and_month(db_session, uow_factory) -> None:
    """Expenses from another family or another month are not counted."""
    owner = await create_test_user(db_session)
    family_one, _ = await create_test_family(db_session, owner)
    family_two, _ = await create_test_family(db_session, owner)
    category_one = await _insert(db_session, family_one, "Groceries")
    category_two = await _insert(db_session, family_two, "Groceries")
    await create_test_expense(db_session, family_one, owner, category_one, amount_cents=1000, year_month="2026-04")
    await create_test_expense(db_session, family_one, owner, category_one, amount_cents=9999, year_month="2026-03")
    await create_test_expense(db_session, family_two, owner, category_two, amount_cents=5000, year_month="2026-04")
    uow = uow_factory(db_session)

    rows = await uow.budget.category_spend_and_goals(family_one.id, "2026-04")

    assert len(rows) == 1
    assert rows[0].spent_cents == 1000
