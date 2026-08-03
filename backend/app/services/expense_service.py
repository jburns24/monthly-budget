"""Expense service: create, list, get, update, and delete expenses.

Behind the repository/UnitOfWork seam (design doc Step 5). ``Family`` and
``Receipt`` are not yet ported (Steps 6 and 7), so ``delete_expense`` still
takes a raw ``AsyncSession`` alongside the ``UnitOfWork`` for the one
cross-aggregate write (deleting a linked Receipt row) that has no repository
yet — the same coexistence the design doc describes for half-migrated routers.

Risk (a): every function that hands an ``Expense`` back to a router uses
``uow.expenses.get_in_family_with_details``, never the bare ``get_in_family``,
because ``ExpenseResponse`` walks ``.category``, ``.user``, and
``.receipt``/``receipt_status``.
"""

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.logging import get_logger
from app.models.category import Category
from app.models.expense import Expense
from app.ports.read_models import CategorySpendRow
from app.ports.unit_of_work import UnitOfWork
from app.schemas.expense import BudgetCategorySummary, BudgetSummaryResponse
from app.services import receipt_storage

logger = get_logger(__name__)


async def _validate_category(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> Category:
    """Validate that a category exists, belongs to the family, and is active.

    Raises HTTPException(400) if the category is invalid.
    """
    category = await uow.categories.get_in_family(category_id, family_id)
    if category is None or not category.is_active:
        raise HTTPException(
            status_code=400,
            detail="Category not found, does not belong to this family, or is inactive",
        )
    return category


async def create_expense(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    category_id: uuid.UUID,
    amount_cents: int,
    description: str,
    expense_date: date,
) -> Expense:
    """Create a new expense for a family.

    Validates the category exists, belongs to the family, and is active.
    Computes year_month from expense_date.
    Returns the Expense with eagerly-loaded category and user.

    Raises HTTPException(400) if the category is invalid.
    """
    await _validate_category(uow, family_id, category_id)

    year_month = expense_date.strftime("%Y-%m")
    now = datetime.now(tz=timezone.utc)

    expense = Expense(
        family_id=family_id,
        user_id=user_id,
        category_id=category_id,
        amount_cents=amount_cents,
        description=description,
        expense_date=expense_date,
        year_month=year_month,
        created_at=now,
        updated_at=now,
    )
    uow.expenses.add(expense)
    await uow.flush()

    reloaded = await uow.expenses.get_in_family_with_details(expense.id, family_id)
    assert reloaded is not None  # just inserted in this same transaction

    logger.info(
        "expense_created",
        expense_id=str(reloaded.id),
        family_id=str(family_id),
        user_id=str(user_id),
        category_id=str(category_id),
        amount_cents=amount_cents,
        year_month=year_month,
    )
    return reloaded


async def list_expenses(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    year_month: str,
    category_id: uuid.UUID | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[Expense], int]:
    """Return paginated expenses for a family filtered by year_month.

    Optionally filter by category_id.
    Orders by expense_date DESC, created_at DESC.
    Returns a tuple of (expenses, total_count).
    """
    total_count = await uow.expenses.count_for_month(family_id, year_month, category_id)

    offset = (page - 1) * per_page
    expenses = await uow.expenses.list_for_month(family_id, year_month, category_id, per_page, offset)

    logger.info(
        "expenses_listed",
        family_id=str(family_id),
        year_month=year_month,
        category_id=str(category_id) if category_id else None,
        page=page,
        per_page=per_page,
        total_count=total_count,
    )
    return expenses, total_count


async def get_expense(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
) -> Expense:
    """Return a single expense with eagerly-loaded relationships.

    Raises HTTPException(404) if not found or not in the family.
    """
    expense = await uow.expenses.get_in_family_with_details(expense_id, family_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense


async def update_expense(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
    expected_updated_at: datetime,
    **fields: Any,
) -> Expense:
    """Partially update an expense with optimistic locking.

    Only updates non-None fields from **fields.
    Raises HTTPException(404) if not found or not in the family.
    Raises HTTPException(409) if expense.updated_at != expected_updated_at (optimistic locking).
    Re-validates category if category_id is changed.
    Re-computes year_month if expense_date is changed.
    """
    expense = await uow.expenses.get_in_family(expense_id, family_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Optimistic locking check — normalize both to UTC for comparison
    expense_updated_at = expense.updated_at
    if expense_updated_at.tzinfo is None:
        expense_updated_at = expense_updated_at.replace(tzinfo=timezone.utc)
    expected = expected_updated_at
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)

    if expense_updated_at != expected:
        raise HTTPException(
            status_code=409,
            detail="Expense has been modified by another request. Please refresh and try again.",
        )

    # Apply non-None field updates
    for field_name, value in fields.items():
        if value is not None:
            setattr(expense, field_name, value)

    # Re-validate category if changed
    if fields.get("category_id") is not None:
        await _validate_category(uow, family_id, fields["category_id"])

    # Re-compute year_month if expense_date changed
    if fields.get("expense_date") is not None:
        expense.year_month = fields["expense_date"].strftime("%Y-%m")

    expense.updated_at = datetime.now(tz=timezone.utc)
    await uow.flush()

    reloaded = await uow.expenses.get_in_family_with_details(expense_id, family_id)
    assert reloaded is not None  # just updated in this same transaction

    logger.info(
        "expense_updated",
        expense_id=str(expense_id),
        family_id=str(family_id),
        updated_fields=list(fields.keys()),
    )
    return reloaded


async def delete_expense(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
) -> None:
    """Hard-delete an expense, cascade-deleting any linked Receipt row and on-disk image.

    Raises HTTPException(404) if not found or not in the family.
    """
    expense = await uow.expenses.get_in_family_with_details(expense_id, family_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    if expense.receipt_id is not None and expense.receipt is not None:
        linked_receipt = expense.receipt
        if linked_receipt.image_path:
            await receipt_storage.delete(Path(linked_receipt.image_path))
        await uow.receipts.delete(linked_receipt)

    await uow.expenses.delete(expense)
    await uow.flush()

    logger.info(
        "expense_deleted",
        expense_id=str(expense_id),
        family_id=str(family_id),
    )


def _compute_status(spent_cents: int, goal_cents: int | None) -> str:
    """Compute spending status relative to goal.

    Returns "none" when no goal is set.
    Returns "green" when spent < 80% of goal.
    Returns "yellow" when spent is 80-99% of goal.
    Returns "red" when spent >= 100% of goal.
    """
    if goal_cents is None or goal_cents == 0:
        return "none"
    percentage = spent_cents / goal_cents
    if percentage >= 1.0:
        return "red"
    if percentage >= 0.8:
        return "yellow"
    return "green"


def build_budget_summary(
    rows: list[CategorySpendRow],
    year_month: str,
    is_editable: bool,
) -> BudgetSummaryResponse:
    """Turn plain spend/goal rows into a BudgetSummaryResponse. Pure — no I/O.

    Design doc Step 5: this is the percentage/status/total math that used to be
    computed inline against the SQL aggregate's rows. Split out, it is
    unit-tested with literal :class:`~app.ports.read_models.CategorySpendRow`
    data (``tests/unit/test_budget_summary.py``); the SQL itself lives in
    ``BudgetQuery.category_spend_and_goals`` and is Postgres-tier only
    (``tests/test_sqlalchemy_adapter.py``).
    """
    category_summaries: list[BudgetCategorySummary] = []
    total_spent_cents = 0

    for row in rows:
        percentage = (row.spent_cents / row.goal_cents) if row.goal_cents else 0.0
        status = _compute_status(row.spent_cents, row.goal_cents)

        category_summaries.append(
            BudgetCategorySummary(
                category_id=row.category_id,
                category_name=row.category_name,
                icon=row.icon,
                spent_cents=row.spent_cents,
                goal_cents=row.goal_cents,
                percentage=round(percentage, 4),
                status=status,
            )
        )
        total_spent_cents += row.spent_cents

    return BudgetSummaryResponse(
        year_month=year_month,
        total_spent_cents=total_spent_cents,
        categories=category_summaries,
        is_editable=is_editable,
    )


async def get_budget_summary(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    year_month: str,
    is_editable: bool,
) -> BudgetSummaryResponse:
    """Return budget summary for a family for the given month.

    ``is_editable`` is computed by the caller (the router queries ``Family``
    directly, same as it already does for the grace-period checks in
    ``update_expense``/``delete_expense`` — ``Family`` has no repository yet,
    design doc Step 6) and passed straight through to the pure
    :func:`build_budget_summary`.
    """
    rows = await uow.budget.category_spend_and_goals(family_id, year_month)
    summary = build_budget_summary(rows, year_month, is_editable)

    logger.info(
        "budget_summary_fetched",
        family_id=str(family_id),
        year_month=year_month,
        category_count=len(summary.categories),
        total_spent_cents=summary.total_spent_cents,
        is_editable=is_editable,
    )
    return summary
