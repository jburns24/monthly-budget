"""Monthly goal service: timezone utilities, rollover, and goal management."""

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.category import Category
from app.models.monthly_goal import MonthlyGoal

logger = get_logger(__name__)


def get_previous_month(year_month: str) -> str:
    """Return the YYYY-MM string for the month preceding the given year_month.

    Parameters
    ----------
    year_month:
        A string in the format "YYYY-MM".

    Returns
    -------
    str
        The previous month in "YYYY-MM" format.

    Example::

        get_previous_month("2026-04")  # returns "2026-03"
        get_previous_month("2026-01")  # returns "2025-12"
    """
    year, month = int(year_month[:4]), int(year_month[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def get_current_budget_month(timezone_str: str) -> str:
    """Return the current budget month (YYYY-MM) in the given timezone.

    Uses zoneinfo.ZoneInfo (Python stdlib) for timezone-aware calculation so
    that families in different timezones see the correct current month.

    Parameters
    ----------
    timezone_str:
        IANA timezone name (e.g. "America/New_York", "Pacific/Auckland").

    Returns
    -------
    str
        The current year-month in "YYYY-MM" format, calculated in the given
        timezone.

    Example::

        get_current_budget_month("America/Los_Angeles")  # e.g. "2026-04"
    """
    tz = ZoneInfo(timezone_str)
    now_local = datetime.now(tz=timezone.utc).astimezone(tz)
    return now_local.strftime("%Y-%m")


async def get_or_check_previous_goals(
    db: AsyncSession,
    family_id: uuid.UUID,
    year_month: str,
) -> tuple[list[MonthlyGoal], bool]:
    """Return goals for the given month, or check whether any previous goals exist.

    - If goals exist for `year_month`, returns (goals, False) — no need to
      prompt the user about rollover because they already have goals.
    - If no goals exist for `year_month`, queries for the most recent prior
      month that has goals and returns ([], True/False) where the boolean
      indicates whether any previous goals were found.

    Parameters
    ----------
    db:
        Active async session.
    family_id:
        The family's UUID.
    year_month:
        The target month in "YYYY-MM" format.

    Returns
    -------
    tuple[list[MonthlyGoal], bool]
        (goals, has_previous_goals) where has_previous_goals is False when
        goals already exist for the requested month.
    """
    # Check whether goals already exist for this month
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month == year_month,
        )
    )
    goals = list(result.scalars().all())
    if goals:
        return goals, False

    # No goals for this month — check if any previous month has goals
    result = await db.execute(
        select(MonthlyGoal.year_month)
        .where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month < year_month,
        )
        .order_by(MonthlyGoal.year_month.desc())
        .limit(1)
    )
    previous_month = result.scalar_one_or_none()
    has_previous_goals = previous_month is not None

    logger.info(
        "get_or_check_previous_goals",
        family_id=str(family_id),
        year_month=year_month,
        has_previous_goals=has_previous_goals,
    )
    return [], has_previous_goals


async def copy_goals_from_previous_month(
    db: AsyncSession,
    family_id: uuid.UUID,
    target_month: str,
) -> int:
    """Copy goals from the most recent previous month to the target month.

    Finds the most recent month before `target_month` that has goals for
    this family, then bulk-copies those goal rows into `target_month`.

    Handles IntegrityError race conditions: if a concurrent request has
    already inserted goals, catches the error, rolls back, and re-reads
    the existing goals to return the actual copied count.

    Parameters
    ----------
    db:
        Active async session.
    family_id:
        The family's UUID.
    target_month:
        The month to copy goals into, in "YYYY-MM" format.

    Returns
    -------
    int
        The number of goals copied (0 if no source month was found).
    """
    # Find the most recent prior month with goals
    result = await db.execute(
        select(MonthlyGoal.year_month)
        .where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month < target_month,
        )
        .order_by(MonthlyGoal.year_month.desc())
        .limit(1)
    )
    source_month = result.scalar_one_or_none()

    if source_month is None:
        logger.info(
            "copy_goals_no_source_found",
            family_id=str(family_id),
            target_month=target_month,
        )
        return 0

    # Load source goals
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month == source_month,
        )
    )
    source_goals = list(result.scalars().all())

    if not source_goals:
        return 0

    # Bulk copy to target month
    new_goals = [
        MonthlyGoal(
            family_id=family_id,
            category_id=goal.category_id,
            year_month=target_month,
            amount_cents=goal.amount_cents,
            version=1,
        )
        for goal in source_goals
    ]

    try:
        db.add_all(new_goals)
        await db.flush()
    except IntegrityError:
        # Race condition: another request already inserted goals — rollback
        # and re-read the existing count
        await db.rollback()
        result = await db.execute(
            select(MonthlyGoal).where(
                MonthlyGoal.family_id == family_id,
                MonthlyGoal.year_month == target_month,
            )
        )
        existing = list(result.scalars().all())
        copied_count = len(existing)
        logger.info(
            "copy_goals_race_condition_handled",
            family_id=str(family_id),
            target_month=target_month,
            existing_count=copied_count,
        )
        return copied_count

    copied_count = len(new_goals)
    logger.info(
        "copy_goals_completed",
        family_id=str(family_id),
        source_month=source_month,
        target_month=target_month,
        copied_count=copied_count,
    )
    return copied_count


async def list_goals(
    db: AsyncSession,
    family_id: uuid.UUID,
    year_month: str,
) -> tuple[list[MonthlyGoal], bool]:
    """List goals for a given month, with rollover hint.

    Delegates to get_or_check_previous_goals to determine whether any
    previous month's goals exist (for frontend rollover prompting).

    Parameters
    ----------
    db:
        Active async session.
    family_id:
        The family's UUID.
    year_month:
        The month to list goals for, in "YYYY-MM" format.

    Returns
    -------
    tuple[list[MonthlyGoal], bool]
        (goals, has_previous_goals). The has_previous_goals flag is True
        when the month has no goals but a prior month does — the frontend
        should offer to copy them.
    """
    return await get_or_check_previous_goals(db, family_id, year_month)


async def _validate_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> Category:
    """Validate that a category exists, belongs to the family, and is active.

    Parameters
    ----------
    db:
        Active async session.
    family_id:
        The family's UUID.
    category_id:
        The category's UUID.

    Returns
    -------
    Category
        The validated category ORM object.

    Raises
    ------
    HTTPException(404)
        If the category does not exist or does not belong to the family.
    HTTPException(400)
        If the category exists but is inactive (archived).
    """
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.family_id == family_id,
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found or does not belong to this family")
    if not category.is_active:
        raise HTTPException(status_code=400, detail="Category is inactive")
    return category


async def create_goal(
    db: AsyncSession,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    year_month: str,
    amount_cents: int,
) -> MonthlyGoal:
    """Create a new monthly goal for a family category.

    Validates that the category exists, belongs to the family, and is active.
    Returns HTTP 409 if a goal for the same family/category/month already exists.

    Parameters
    ----------
    db:
        Active async session.
    family_id:
        The family's UUID.
    category_id:
        The category's UUID.
    year_month:
        The target month in "YYYY-MM" format.
    amount_cents:
        The budget goal amount in cents (must be positive).

    Returns
    -------
    MonthlyGoal
        The newly created MonthlyGoal ORM object.

    Raises
    ------
    HTTPException(404)
        If the category is not found or does not belong to the family.
    HTTPException(400)
        If the category is inactive.
    HTTPException(409)
        If a goal already exists for this family/category/month.
    """
    await _validate_category(db, family_id, category_id)

    goal = MonthlyGoal(
        family_id=family_id,
        category_id=category_id,
        year_month=year_month,
        amount_cents=amount_cents,
        version=1,
    )
    db.add(goal)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A goal for this category and month already exists",
        )

    await db.refresh(goal)
    logger.info(
        "goal_created",
        goal_id=str(goal.id),
        family_id=str(family_id),
        category_id=str(category_id),
        year_month=year_month,
        amount_cents=amount_cents,
    )
    return goal


async def update_goal(
    db: AsyncSession,
    goal_id: uuid.UUID,
    family_id: uuid.UUID,
    amount_cents: int,
    expected_version: int,
) -> MonthlyGoal:
    """Update the amount of an existing monthly goal with optimistic locking.

    Checks that the goal exists and belongs to the family, then compares
    expected_version against the current version. Increments version on success.

    Parameters
    ----------
    db:
        Active async session.
    goal_id:
        The goal's UUID.
    family_id:
        The family's UUID (for ownership check).
    amount_cents:
        The new budget goal amount in cents.
    expected_version:
        The version the caller believes is current. Must match to proceed.

    Returns
    -------
    MonthlyGoal
        The updated MonthlyGoal ORM object.

    Raises
    ------
    HTTPException(404)
        If the goal does not exist or does not belong to the family.
    HTTPException(409)
        If expected_version does not match the current version (conflict).
    """
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.id == goal_id,
            MonthlyGoal.family_id == family_id,
        )
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    if goal.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail="Goal has been modified by another request. Please refresh and try again.",
        )

    goal.amount_cents = amount_cents
    goal.version = goal.version + 1
    await db.flush()
    await db.refresh(goal)

    logger.info(
        "goal_updated",
        goal_id=str(goal_id),
        family_id=str(family_id),
        amount_cents=amount_cents,
        new_version=goal.version,
    )
    return goal


async def delete_goal(
    db: AsyncSession,
    goal_id: uuid.UUID,
    family_id: uuid.UUID,
) -> None:
    """Hard-delete a monthly goal.

    Parameters
    ----------
    db:
        Active async session.
    goal_id:
        The goal's UUID.
    family_id:
        The family's UUID (for ownership check).

    Raises
    ------
    HTTPException(404)
        If the goal does not exist or does not belong to the family.
    """
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.id == goal_id,
            MonthlyGoal.family_id == family_id,
        )
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    await db.delete(goal)
    await db.flush()

    logger.info(
        "goal_deleted",
        goal_id=str(goal_id),
        family_id=str(family_id),
    )


async def bulk_upsert_goals(
    db: AsyncSession,
    family_id: uuid.UUID,
    year_month: str,
    goals_list: list[dict],
) -> dict:
    """Bulk upsert goals for a family month — all-or-nothing transaction.

    For each entry in goals_list (each containing ``category_id`` and
    ``amount_cents``):

    - If no goal exists for that category/month, create it (count as created).
    - If a goal exists, update its amount and increment its version (count as
      updated).

    Goals currently in the database for ``family_id``/``year_month`` that are
    **not** represented in ``goals_list`` are deleted (count as deleted).

    All changes are applied within a single flush so the database either
    accepts all of them or none.

    Parameters
    ----------
    db:
        Active async session (the caller is responsible for commit/rollback).
    family_id:
        The family's UUID.
    year_month:
        The target month in "YYYY-MM" format.
    goals_list:
        A list of dicts, each with keys ``category_id`` (uuid.UUID) and
        ``amount_cents`` (int).

    Returns
    -------
    dict
        ``{"created": int, "updated": int, "deleted": int}`` counts.

    Raises
    ------
    HTTPException(404)
        If any category does not exist or does not belong to the family.
    HTTPException(400)
        If any category is inactive.
    """
    # Validate all categories first — fail fast before touching DB
    for item in goals_list:
        await _validate_category(db, family_id, item["category_id"])

    # Fetch existing goals for this family+month
    result = await db.execute(
        select(MonthlyGoal).where(
            MonthlyGoal.family_id == family_id,
            MonthlyGoal.year_month == year_month,
        )
    )
    existing_goals = {g.category_id: g for g in result.scalars().all()}

    incoming_category_ids = {item["category_id"] for item in goals_list}

    created = 0
    updated = 0

    for item in goals_list:
        cat_id = item["category_id"]
        amount = item["amount_cents"]
        if cat_id in existing_goals:
            existing = existing_goals[cat_id]
            existing.amount_cents = amount
            existing.version = existing.version + 1
            updated += 1
        else:
            new_goal = MonthlyGoal(
                family_id=family_id,
                category_id=cat_id,
                year_month=year_month,
                amount_cents=amount,
                version=1,
            )
            db.add(new_goal)
            created += 1

    # Delete goals not in the incoming list
    goals_to_delete = [g for cat_id, g in existing_goals.items() if cat_id not in incoming_category_ids]
    deleted = len(goals_to_delete)
    for goal in goals_to_delete:
        await db.delete(goal)

    await db.flush()

    logger.info(
        "bulk_upsert_goals_completed",
        family_id=str(family_id),
        year_month=year_month,
        created=created,
        updated=updated,
        deleted=deleted,
    )
    return {"created": created, "updated": updated, "deleted": deleted}
