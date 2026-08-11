"""Unit tests for the in-memory ExpenseRepository. No database.

Risk (a) is the focus here: ``get_in_family_with_details`` and
``list_for_month`` must populate ``.category``, ``.user``, and ``.receipt`` on
every row they return, or ``ExpenseResponse.model_validate`` (which walks all
three) fails — silently or loudly depending on the field.
"""

import uuid
from datetime import date

import pytest

from app.ports.errors import UniqueViolation
from app.schemas.expense import ExpenseResponse
from tests.unit.conftest import make_category, make_expense, make_receipt, make_user, seed


async def _seed_expense_with_relations(uow, family_id, *, receipt_status: str | None = "completed"):
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    receipt = None
    if receipt_status is not None:
        receipt = make_receipt(family_id, user.id, status=receipt_status)
        await seed(uow, receipt)
    expense = make_expense(
        family_id,
        category.id,
        user_id=user.id,
        receipt_id=receipt.id if receipt is not None else None,
    )
    await seed(uow, expense)
    return category, user, receipt, expense


# ---------------------------------------------------------------------------
# get_in_family (bare — no relationships)
# ---------------------------------------------------------------------------


async def test_get_in_family_returns_the_expense(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)
    await seed(uow, expense)

    found = await uow.expenses.get_in_family(expense.id, family_id)

    assert found is not None
    assert found.id == expense.id


async def test_get_in_family_returns_none_for_another_familys_expense(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)
    await seed(uow, expense)

    assert await uow.expenses.get_in_family(expense.id, uuid.uuid4()) is None


async def test_get_in_family_returns_none_for_an_unknown_id(uow, family_id) -> None:
    assert await uow.expenses.get_in_family(uuid.uuid4(), family_id) is None


# ---------------------------------------------------------------------------
# get_in_family_with_details — risk (a)
# ---------------------------------------------------------------------------


async def test_get_in_family_with_details_populates_category_and_user(uow, family_id) -> None:
    category, user, _, expense = await _seed_expense_with_relations(uow, family_id, receipt_status=None)

    found = await uow.expenses.get_in_family_with_details(expense.id, family_id)

    assert found is not None
    assert found.category is not None
    assert found.category.id == category.id
    assert found.user is not None
    assert found.user.id == user.id
    assert found.receipt is None
    assert found.receipt_status is None


async def test_get_in_family_with_details_populates_receipt(uow, family_id) -> None:
    _, _, receipt, expense = await _seed_expense_with_relations(uow, family_id, receipt_status="completed")

    found = await uow.expenses.get_in_family_with_details(expense.id, family_id)

    assert found is not None
    assert found.receipt is not None
    assert found.receipt.id == receipt.id
    assert found.receipt_status == "completed"


async def test_get_in_family_with_details_survives_model_validate(uow, family_id) -> None:
    """The actual risk (a) failure mode: ExpenseResponse.model_validate walks all three relationships."""
    _, _, _, expense = await _seed_expense_with_relations(uow, family_id, receipt_status="processing")

    found = await uow.expenses.get_in_family_with_details(expense.id, family_id)
    response = ExpenseResponse.model_validate(found)

    assert response.category is not None
    assert response.category.name == "Groceries"
    assert response.created_by_user.id == expense.user_id
    assert response.receipt_status == "processing"


async def test_get_in_family_with_details_returns_none_for_an_unknown_id(uow, family_id) -> None:
    assert await uow.expenses.get_in_family_with_details(uuid.uuid4(), family_id) is None


# ---------------------------------------------------------------------------
# list_for_month
# ---------------------------------------------------------------------------


async def test_list_for_month_is_scoped_to_family_and_month(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    other_family = uuid.uuid4()
    await seed(
        uow,
        make_expense(family_id, category.id, user_id=user.id, year_month="2026-04"),
        make_expense(family_id, category.id, user_id=user.id, year_month="2026-03"),
        make_expense(other_family, category.id, user_id=user.id, year_month="2026-04"),
    )

    results = await uow.expenses.list_for_month(family_id, "2026-04", None, 50, 0)

    assert len(results) == 1


async def test_list_for_month_filters_by_category(uow, family_id) -> None:
    groceries = make_category(family_id, "Groceries")
    transport = make_category(family_id, "Transport")
    user = make_user()
    await seed(uow, groceries, transport, user)
    await seed(
        uow,
        make_expense(family_id, groceries.id, user_id=user.id),
        make_expense(family_id, transport.id, user_id=user.id),
    )

    results = await uow.expenses.list_for_month(family_id, "2026-04", groceries.id, 50, 0)

    assert len(results) == 1
    assert results[0].category_id == groceries.id


async def test_list_for_month_filters_by_entry_type(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        make_expense(family_id, category.id, user_id=user.id),
        make_expense(family_id, None, user_id=user.id, entry_type="income", description="Paycheck"),
    )

    income = await uow.expenses.list_for_month(family_id, "2026-04", None, 50, 0, entry_type="income")
    expenses = await uow.expenses.list_for_month(family_id, "2026-04", None, 50, 0, entry_type="expense")

    assert len(income) == 1
    assert income[0].entry_type == "income"
    assert income[0].category is None
    assert len(expenses) == 1
    assert expenses[0].entry_type == "expense"


async def test_count_for_month_filters_by_entry_type(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        make_expense(family_id, category.id, user_id=user.id),
        make_expense(family_id, category.id, user_id=user.id),
        make_expense(family_id, None, user_id=user.id, entry_type="income"),
    )

    assert await uow.expenses.count_for_month(family_id, "2026-04", None, entry_type="income") == 1
    assert await uow.expenses.count_for_month(family_id, "2026-04", None, entry_type="expense") == 2


async def test_duplicate_starting_balance_raises_unique_violation(uow, family_id) -> None:
    """Partial unique index uq_expenses_starting_balance_per_family_month."""
    user = make_user()
    await seed(uow, user)
    await seed(
        uow,
        make_expense(
            family_id,
            None,
            user_id=user.id,
            entry_type="income",
            is_starting_balance=True,
            year_month="2026-04",
        ),
    )
    uow.expenses.add(
        make_expense(
            family_id,
            None,
            user_id=user.id,
            entry_type="income",
            is_starting_balance=True,
            year_month="2026-04",
            description="Second",
        )
    )

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_expenses_starting_balance_per_family_month"


async def test_list_for_month_orders_newest_first(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    early = make_expense(family_id, category.id, user_id=user.id, expense_date=date(2026, 4, 1))
    late = make_expense(family_id, category.id, user_id=user.id, expense_date=date(2026, 4, 15))
    await seed(uow, early, late)

    results = await uow.expenses.list_for_month(family_id, "2026-04", None, 50, 0)

    assert [e.id for e in results] == [late.id, early.id]


async def test_list_for_month_paginates_with_limit_and_offset(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        *[make_expense(family_id, category.id, user_id=user.id, expense_date=date(2026, 4, i)) for i in range(1, 6)],
    )

    page = await uow.expenses.list_for_month(family_id, "2026-04", None, 2, 2)

    assert len(page) == 2


async def test_list_for_month_populates_relationships_on_every_row(uow, family_id) -> None:
    await _seed_expense_with_relations(uow, family_id)

    (result,) = await uow.expenses.list_for_month(family_id, "2026-04", None, 50, 0)

    assert result.category is not None
    assert result.user is not None
    assert result.receipt is not None


# ---------------------------------------------------------------------------
# count_for_month
# ---------------------------------------------------------------------------


async def test_count_for_month_matches_list_for_month(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(uow, *[make_expense(family_id, category.id, user_id=user.id) for _ in range(3)])

    assert await uow.expenses.count_for_month(family_id, "2026-04", None) == 3


async def test_count_for_month_filters_by_category(uow, family_id) -> None:
    groceries = make_category(family_id, "Groceries")
    transport = make_category(family_id, "Transport")
    user = make_user()
    await seed(uow, groceries, transport, user)
    await seed(
        uow,
        make_expense(family_id, groceries.id, user_id=user.id),
        make_expense(family_id, transport.id, user_id=user.id),
        make_expense(family_id, transport.id, user_id=user.id),
    )

    assert await uow.expenses.count_for_month(family_id, "2026-04", transport.id) == 2


# ---------------------------------------------------------------------------
# count_by_category (extended, not duplicated, from the Category pilot)
# ---------------------------------------------------------------------------


async def test_count_by_category_counts_across_months(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    await seed(
        uow,
        make_expense(family_id, category.id, year_month="2026-04"),
        make_expense(family_id, category.id, year_month="2026-03"),
    )

    assert await uow.expenses.count_by_category(category.id) == 2


# ---------------------------------------------------------------------------
# add / delete
# ---------------------------------------------------------------------------


async def test_add_then_flush_makes_the_expense_visible(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)

    uow.expenses.add(expense)
    assert await uow.expenses.count_for_month(family_id, "2026-04", None) == 0

    await uow.flush()

    assert await uow.expenses.count_for_month(family_id, "2026-04", None) == 1


async def test_delete_removes_the_row_on_flush(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)
    await seed(uow, expense)

    await uow.expenses.delete(expense)
    await uow.flush()

    assert await uow.expenses.get_in_family(expense.id, family_id) is None
