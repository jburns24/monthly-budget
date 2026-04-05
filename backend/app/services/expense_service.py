"""Expense service: create, list, get, update, and delete expenses."""

import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.logging import get_logger
from app.models.category import Category
from app.models.expense import Expense
from app.models.monthly_goal import MonthlyGoal
from app.schemas.expense import BudgetCategorySummary, BudgetSummaryResponse

logger = get_logger(__name__)


async def _validate_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> Category:
    """Validate that a category exists, belongs to the family, and is active.

    Raises HTTPException(400) if the category is invalid.
    """
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.family_id == family_id,
        )
    )
    category = result.scalar_one_or_none()
    if category is None or not category.is_active:
        raise HTTPException(
            status_code=400,
            detail="Category not found, does not belong to this family, or is inactive",
        )
    return category


async def create_expense(
    db: AsyncSession,
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
    await _validate_category(db, family_id, category_id)

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
    db.add(expense)
    await db.flush()

    # Reload with eager-loaded relationships via selectinload
    result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.category), selectinload(Expense.user))
        .where(Expense.id == expense.id)
    )
    expense = result.scalar_one()

    logger.info(
        "expense_created",
        expense_id=str(expense.id),
        family_id=str(family_id),
        user_id=str(user_id),
        category_id=str(category_id),
        amount_cents=amount_cents,
        year_month=year_month,
    )
    return expense


async def list_expenses(
    db: AsyncSession,
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
    base_filters = [
        Expense.family_id == family_id,
        Expense.year_month == year_month,
    ]
    if category_id is not None:
        base_filters.append(Expense.category_id == category_id)

    # Count query
    count_result = await db.execute(select(func.count()).select_from(Expense).where(*base_filters))
    total_count = count_result.scalar_one()

    # Data query with eager loading and pagination
    offset = (page - 1) * per_page
    data_result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.category), selectinload(Expense.user))
        .where(*base_filters)
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    expenses = list(data_result.scalars().all())

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
    db: AsyncSession,
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
) -> Expense:
    """Return a single expense with eagerly-loaded relationships.

    Raises HTTPException(404) if not found or not in the family.
    """
    result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.category), selectinload(Expense.user))
        .where(Expense.id == expense_id, Expense.family_id == family_id)
    )
    expense = result.scalar_one_or_none()
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense


async def update_expense(
    db: AsyncSession,
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
    result = await db.execute(select(Expense).where(Expense.id == expense_id, Expense.family_id == family_id))
    expense = result.scalar_one_or_none()
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
        await _validate_category(db, family_id, fields["category_id"])

    # Re-compute year_month if expense_date changed
    if fields.get("expense_date") is not None:
        expense.year_month = fields["expense_date"].strftime("%Y-%m")

    expense.updated_at = datetime.now(tz=timezone.utc)
    await db.flush()

    # Reload with eager-loaded relationships via selectinload
    reload_result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.category), selectinload(Expense.user))
        .where(Expense.id == expense_id)
    )
    expense = reload_result.scalar_one()

    logger.info(
        "expense_updated",
        expense_id=str(expense_id),
        family_id=str(family_id),
        updated_fields=list(fields.keys()),
    )
    return expense


async def delete_expense(
    db: AsyncSession,
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
) -> None:
    """Hard-delete an expense.

    Raises HTTPException(404) if not found or not in the family.
    """
    result = await db.execute(select(Expense).where(Expense.id == expense_id, Expense.family_id == family_id))
    expense = result.scalar_one_or_none()
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    await db.delete(expense)
    await db.flush()

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


async def get_budget_summary(
    db: AsyncSession,
    family_id: uuid.UUID,
    year_month: str,
) -> BudgetSummaryResponse:
    """Return budget summary for a family for the given month.

    Executes a single aggregation query joining categories with expenses and
    monthly_goals for the given family and year_month. Only includes active
    categories belonging to the family.

    Returns per-category data (spent, goal, percentage, status) and total_spent_cents.
    """
    # Build a scalar subquery for goal_cents per category
    goal_subq = (
        select(MonthlyGoal.category_id, MonthlyGoal.amount_cents)
        .where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month == year_month,
        )
        .subquery()
    )

    # Build the aggregation query:
    # SELECT categories.*, SUM(expenses.amount_cents), goal_subq.amount_cents
    # FROM categories
    # LEFT JOIN expenses ON expenses.category_id = categories.id AND ...
    # LEFT JOIN goal_subq ON goal_subq.category_id = categories.id
    # WHERE categories.family_id = ? AND categories.is_active = true
    # GROUP BY categories.id, goal_subq.amount_cents
    expenses_filtered = outerjoin(
        Category,
        Expense,
        (Expense.category_id == Category.id) & (Expense.family_id == family_id) & (Expense.year_month == year_month),
    ).outerjoin(
        goal_subq,
        goal_subq.c.category_id == Category.id,
    )

    stmt = (
        select(
            Category.id,
            Category.name,
            Category.icon,
            func.coalesce(func.sum(Expense.amount_cents), 0).label("spent_cents"),
            goal_subq.c.amount_cents.label("goal_cents"),
        )
        .select_from(expenses_filtered)
        .where(
            Category.family_id == family_id,
            Category.is_active.is_(True),
        )
        .group_by(Category.id, Category.name, Category.icon, goal_subq.c.amount_cents)
        .order_by(Category.sort_order, Category.name)
    )

    result = await db.execute(stmt)
    rows = result.all()

    category_summaries: list[BudgetCategorySummary] = []
    total_spent_cents = 0

    for row in rows:
        spent = int(row.spent_cents)
        goal: int | None = int(row.goal_cents) if row.goal_cents is not None else None
        percentage = (spent / goal) if goal else 0.0
        status = _compute_status(spent, goal)

        category_summaries.append(
            BudgetCategorySummary(
                category_id=row.id,
                category_name=row.name,
                icon=row.icon,
                spent_cents=spent,
                goal_cents=goal,
                percentage=round(percentage, 4),
                status=status,
            )
        )
        total_spent_cents += spent

    logger.info(
        "budget_summary_fetched",
        family_id=str(family_id),
        year_month=year_month,
        category_count=len(category_summaries),
        total_spent_cents=total_spent_cents,
    )

    return BudgetSummaryResponse(
        year_month=year_month,
        total_spent_cents=total_spent_cents,
        categories=category_summaries,
    )
