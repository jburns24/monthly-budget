"""Unit tests for expense_service against the in-memory adapter. No database.

Postgres-tier coverage — including ``get_budget_summary``'s 5-way SQL aggregate,
which has no fake — lives in ``tests/test_expenses_service.py`` and
``tests/test_expenses_api.py``. This module proves the CRUD paths (create,
list, get, update) work identically without a connection, and is the primary
place risk (a) — every returned ``Expense`` needing ``.category``/``.user``/
``.receipt`` populated — gets exercised.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.schemas.expense import ExpenseResponse
from app.services.expense_service import (
    create_expense,
    get_expense,
    list_expenses,
    update_expense,
)
from tests.unit.conftest import make_category, make_expense, make_user, seed

# ---------------------------------------------------------------------------
# create_expense
# ---------------------------------------------------------------------------


async def test_create_expense_returns_a_populated_expense(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    user = make_user()
    await seed(uow, user)

    expense = await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=4523,
        description="Weekly shop",
        expense_date=date(2026, 4, 1),
    )

    assert expense.family_id == family_id
    assert expense.category_id == category.id
    assert expense.user_id == user.id
    assert expense.amount_cents == 4523
    assert expense.year_month == "2026-04"
    assert isinstance(expense.id, uuid.UUID)


async def test_create_expense_eager_loads_category_and_user(uow, family_id) -> None:
    """Risk (a): the returned instance must satisfy ExpenseResponse.model_validate."""
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)

    expense = await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=1000,
        description="Test",
        expense_date=date(2026, 4, 1),
    )

    response = ExpenseResponse.model_validate(expense)
    assert response.category is not None
    assert response.category.id == category.id
    assert response.created_by_user.id == user.id
    assert response.receipt_status is None


async def test_create_expense_rejects_an_inactive_category(uow, family_id) -> None:
    category = make_category(family_id, "Archived", is_active=False)
    await seed(uow, category)
    user = make_user()
    await seed(uow, user)

    with pytest.raises(HTTPException) as exc_info:
        await create_expense(
            uow,
            family_id=family_id,
            user_id=user.id,
            category_id=category.id,
            amount_cents=1000,
            description="Test",
            expense_date=date(2026, 4, 1),
        )

    assert exc_info.value.status_code == 400


async def test_create_expense_rejects_a_nonexistent_category(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_expense(
            uow,
            family_id=family_id,
            user_id=uuid.uuid4(),
            category_id=uuid.uuid4(),
            amount_cents=1000,
            description="Test",
            expense_date=date(2026, 4, 1),
        )

    assert exc_info.value.status_code == 400


async def test_create_expense_computes_year_month(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)

    expense = await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=2500,
        description="December purchase",
        expense_date=date(2025, 12, 15),
    )

    assert expense.year_month == "2025-12"


async def test_create_income_without_category(uow, family_id) -> None:
    """Income skips category validation and persists with a null category."""
    user = make_user()
    await seed(uow, user)

    expense = await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=None,
        amount_cents=250000,
        description="Paycheck",
        expense_date=date(2026, 4, 1),
        entry_type="income",
    )

    assert expense.entry_type == "income"
    assert expense.category_id is None
    assert expense.is_starting_balance is False
    response = ExpenseResponse.model_validate(expense)
    assert response.category is None
    assert response.entry_type == "income"


async def test_create_starting_balance_sets_flags(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)

    expense = await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=None,
        amount_cents=100000,
        description="Opening balance",
        expense_date=date(2026, 4, 1),
        entry_type="income",
        is_starting_balance=True,
    )

    assert expense.entry_type == "income"
    assert expense.is_starting_balance is True


async def test_create_second_starting_balance_in_same_month_raises_409(uow, family_id) -> None:
    """The unique partial index translation drives the 409 — no database needed."""
    user = make_user()
    await seed(uow, user)
    await create_expense(
        uow,
        family_id=family_id,
        user_id=user.id,
        category_id=None,
        amount_cents=100000,
        description="Opening balance",
        expense_date=date(2026, 4, 1),
        entry_type="income",
        is_starting_balance=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_expense(
            uow,
            family_id=family_id,
            user_id=user.id,
            category_id=None,
            amount_cents=50000,
            description="Duplicate opening",
            expense_date=date(2026, 4, 15),
            entry_type="income",
            is_starting_balance=True,
        )

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# list_expenses / get_expense
# ---------------------------------------------------------------------------


async def test_list_expenses_filters_by_year_month(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        *[
            make_expense(family_id, category.id, user_id=user.id, year_month="2026-04", expense_date=date(2026, 4, 1))
            for _ in range(3)
        ],
        *[
            make_expense(family_id, category.id, user_id=user.id, year_month="2026-03", expense_date=date(2026, 3, 1))
            for _ in range(2)
        ],
    )

    expenses, total_count = await list_expenses(uow, family_id, year_month="2026-04")

    assert len(expenses) == 3
    assert total_count == 3
    assert all(e.year_month == "2026-04" for e in expenses)


async def test_list_expenses_pagination(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        *[
            make_expense(
                family_id,
                category.id,
                user_id=user.id,
                year_month="2026-04",
                expense_date=date(2026, 4, 1),
                amount_cents=100 + i,
            )
            for i in range(75)
        ],
    )

    expenses, total_count = await list_expenses(uow, family_id, year_month="2026-04", page=2, per_page=50)

    assert len(expenses) == 25
    assert total_count == 75


async def test_list_expenses_filters_by_category(uow, family_id) -> None:
    groceries = make_category(family_id, "Groceries")
    transport = make_category(family_id, "Transport")
    user = make_user()
    await seed(uow, groceries, transport, user)
    await seed(
        uow,
        *[make_expense(family_id, groceries.id, user_id=user.id, year_month="2026-04") for _ in range(3)],
        *[make_expense(family_id, transport.id, user_id=user.id, year_month="2026-04") for _ in range(2)],
    )

    expenses, total_count = await list_expenses(uow, family_id, year_month="2026-04", category_id=groceries.id)

    assert len(expenses) == 3
    assert total_count == 3
    assert all(e.category_id == groceries.id for e in expenses)


async def test_list_expenses_filters_by_entry_type(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    await seed(
        uow,
        make_expense(family_id, category.id, user_id=user.id, year_month="2026-04"),
        make_expense(family_id, category.id, user_id=user.id, year_month="2026-04"),
        make_expense(
            family_id,
            None,
            user_id=user.id,
            year_month="2026-04",
            entry_type="income",
            description="Paycheck",
        ),
    )

    income, income_count = await list_expenses(uow, family_id, year_month="2026-04", entry_type="income")
    expenses, expense_count = await list_expenses(uow, family_id, year_month="2026-04", entry_type="expense")

    assert income_count == 1
    assert len(income) == 1
    assert income[0].entry_type == "income"
    assert expense_count == 2
    assert all(e.entry_type == "expense" for e in expenses)


async def test_get_expense_returns_it_with_details(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    expense = make_expense(family_id, category.id, user_id=user.id)
    await seed(uow, expense)

    found = await get_expense(uow, family_id=family_id, expense_id=expense.id)

    assert found.id == expense.id
    assert found.category is not None
    assert found.user is not None


async def test_get_expense_raises_404_for_an_unknown_id(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_expense(uow, family_id=family_id, expense_id=uuid.uuid4())

    assert exc_info.value.status_code == 404


async def test_get_expense_raises_404_for_another_familys_expense(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)
    await seed(uow, expense)

    with pytest.raises(HTTPException) as exc_info:
        await get_expense(uow, family_id=uuid.uuid4(), expense_id=expense.id)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# update_expense
# ---------------------------------------------------------------------------


async def test_update_expense_changes_only_the_given_fields(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id, amount_cents=4523, description="Weekly shop")
    await seed(uow, expense)

    updated = await update_expense(
        uow,
        family_id=family_id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        description="Monthly shop",
    )

    assert updated.description == "Monthly shop"
    assert updated.amount_cents == 4523


async def test_update_expense_eager_loads_after_the_reload(uow, family_id) -> None:
    """Risk (a): the post-update reload must also populate relationships."""
    category = make_category(family_id, "Groceries")
    user = make_user()
    await seed(uow, category, user)
    expense = make_expense(family_id, category.id, user_id=user.id)
    await seed(uow, expense)

    updated = await update_expense(
        uow,
        family_id=family_id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        amount_cents=9999,
    )

    response = ExpenseResponse.model_validate(updated)
    assert response.category is not None
    assert response.category.id == category.id
    assert response.created_by_user.id == user.id


async def test_update_expense_raises_409_on_a_stale_updated_at(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id)
    await seed(uow, expense)
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        await update_expense(
            uow,
            family_id=family_id,
            expense_id=expense.id,
            expected_updated_at=stale,
            description="Should fail",
        )

    assert exc_info.value.status_code == 409


async def test_update_expense_recomputes_year_month(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    expense = make_expense(family_id, category.id, expense_date=date(2026, 4, 1), year_month="2026-04")
    await seed(uow, expense)

    updated = await update_expense(
        uow,
        family_id=family_id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        expense_date=date(2026, 3, 15),
    )

    assert updated.year_month == "2026-03"


async def test_update_expense_raises_404_for_an_unknown_id(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_expense(
            uow,
            family_id=family_id,
            expense_id=uuid.uuid4(),
            expected_updated_at=datetime.now(tz=timezone.utc),
            description="X",
        )

    assert exc_info.value.status_code == 404


async def test_update_income_skips_category_validation(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)
    expense = make_expense(
        family_id,
        None,
        user_id=user.id,
        entry_type="income",
        amount_cents=10000,
        description="Paycheck",
    )
    await seed(uow, expense)

    updated = await update_expense(
        uow,
        family_id=family_id,
        expense_id=expense.id,
        expected_updated_at=expense.updated_at,
        description="Updated paycheck",
        entry_type="income",
    )

    assert updated.description == "Updated paycheck"
    assert updated.category_id is None
    assert updated.entry_type == "income"
    response = ExpenseResponse.model_validate(updated)
    assert response.category is None
