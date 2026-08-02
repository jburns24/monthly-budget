"""Monthly goal service: timezone utilities, rollover, and goal management.

Behind the repository/UnitOfWork seam (design doc Step 4): no ``AsyncSession``,
no ``select()``, no ``sqlalchemy.exc.IntegrityError``. The 409 paths key on
:class:`~app.ports.errors.UniqueViolation`, which the SQLAlchemy adapter
translates ``IntegrityError`` into and the in-memory adapter raises directly —
the same seam ``category_service`` uses.
"""

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.logging import get_logger
from app.models.category import Category
from app.models.monthly_goal import MonthlyGoal
from app.ports.errors import UniqueViolation
from app.ports.unit_of_work import UnitOfWork

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
    uow: UnitOfWork,
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
    uow:
        Active UnitOfWork.
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
    goals = await uow.goals.list_for_month(family_id, year_month)
    if goals:
        return goals, False

    previous_month = await uow.goals.latest_month_before(family_id, year_month)
    has_previous_goals = previous_month is not None

    logger.info(
        "get_or_check_previous_goals",
        family_id=str(family_id),
        year_month=year_month,
        has_previous_goals=has_previous_goals,
    )
    return [], has_previous_goals


async def copy_goals_from_previous_month(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    target_month: str,
) -> int:
    """Copy goals from the most recent previous month to the target month.

    Finds the most recent month before `target_month` that has goals for
    this family, then bulk-copies those goal rows into `target_month`.

    Handles a duplicate-key race: if a concurrent request has already
    inserted goals, catches the resulting UniqueViolation, rolls back, and
    re-reads the existing goals to return the actual copied count.

    NOTE (design doc risk (f)): ``uow.rollback()`` here discards the *whole*
    request, not just the failed insert — ported literally from the
    pre-seam ``db.rollback()`` call to preserve behaviour. The correct fix is
    a savepoint, and that is a behaviour change deserving its own PR.

    Parameters
    ----------
    uow:
        Active UnitOfWork.
    family_id:
        The family's UUID.
    target_month:
        The month to copy goals into, in "YYYY-MM" format.

    Returns
    -------
    int
        The number of goals copied (0 if no source month was found).
    """
    source_month = await uow.goals.latest_month_before(family_id, target_month)

    if source_month is None:
        logger.info(
            "copy_goals_no_source_found",
            family_id=str(family_id),
            target_month=target_month,
        )
        return 0

    source_goals = await uow.goals.list_for_month(family_id, source_month)

    if not source_goals:
        return 0

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
        uow.goals.add_all(new_goals)
        await uow.flush()
    except UniqueViolation:
        # Race condition: another request already inserted goals — rollback
        # (the whole request, see NOTE above) and re-read the existing count.
        await uow.rollback()
        existing = await uow.goals.list_for_month(family_id, target_month)
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
    uow: UnitOfWork,
    family_id: uuid.UUID,
    year_month: str,
) -> tuple[list[MonthlyGoal], bool]:
    """List goals for a given month, with rollover hint.

    Delegates to get_or_check_previous_goals to determine whether any
    previous month's goals exist (for frontend rollover prompting).

    Parameters
    ----------
    uow:
        Active UnitOfWork.
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
    return await get_or_check_previous_goals(uow, family_id, year_month)


async def _validate_category(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> Category:
    """Validate that a category exists, belongs to the family, and is active.

    Parameters
    ----------
    uow:
        Active UnitOfWork.
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
    category = await uow.categories.get_in_family(category_id, family_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found or does not belong to this family")
    if not category.is_active:
        raise HTTPException(status_code=400, detail="Category is inactive")
    return category


async def create_goal(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    year_month: str,
    amount_cents: int,
) -> MonthlyGoal:
    """Create a new monthly goal for a family category.

    Validates that the category exists, belongs to the family, and is active.
    Returns HTTP 409 if a goal for the same family/category/month already exists.

    NOTE (design doc risk (f)): the 409 path calls ``uow.rollback()``, which
    discards the *whole* request, not just the failed insert — ported
    literally from the pre-seam ``db.rollback()`` call. The correct fix is a
    savepoint, and that is a behaviour change deserving its own PR.

    Parameters
    ----------
    uow:
        Active UnitOfWork.
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
    await _validate_category(uow, family_id, category_id)

    goal = MonthlyGoal(
        family_id=family_id,
        category_id=category_id,
        year_month=year_month,
        amount_cents=amount_cents,
        version=1,
    )
    uow.goals.add(goal)
    try:
        await uow.flush()
    except UniqueViolation:
        await uow.rollback()
        raise HTTPException(
            status_code=409,
            detail="A goal for this category and month already exists",
        )

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
    uow: UnitOfWork,
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
    uow:
        Active UnitOfWork.
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
    goal = await uow.goals.get_in_family(goal_id, family_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    if goal.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail="Goal has been modified by another request. Please refresh and try again.",
        )

    # No add() call: the repository hands back a tracked instance, so mutating
    # it and flushing is the update (design doc risk (b)).
    goal.amount_cents = amount_cents
    goal.version = goal.version + 1
    await uow.flush()

    logger.info(
        "goal_updated",
        goal_id=str(goal_id),
        family_id=str(family_id),
        amount_cents=amount_cents,
        new_version=goal.version,
    )
    return goal


async def delete_goal(
    uow: UnitOfWork,
    goal_id: uuid.UUID,
    family_id: uuid.UUID,
) -> None:
    """Hard-delete a monthly goal.

    Parameters
    ----------
    uow:
        Active UnitOfWork.
    goal_id:
        The goal's UUID.
    family_id:
        The family's UUID (for ownership check).

    Raises
    ------
    HTTPException(404)
        If the goal does not exist or does not belong to the family.
    """
    goal = await uow.goals.get_in_family(goal_id, family_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    await uow.goals.delete(goal)
    await uow.flush()

    logger.info(
        "goal_deleted",
        goal_id=str(goal_id),
        family_id=str(family_id),
    )


async def bulk_upsert_goals(
    uow: UnitOfWork,
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
    uow:
        Active UnitOfWork (the caller is responsible for commit/rollback).
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
    # Validate all categories first — fail fast before touching the store.
    for item in goals_list:
        await _validate_category(uow, family_id, item["category_id"])

    existing_goals = {g.category_id: g for g in await uow.goals.list_for_month(family_id, year_month)}

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
            uow.goals.add(new_goal)
            created += 1

    # Delete goals not in the incoming list
    goals_to_delete = [g for cat_id, g in existing_goals.items() if cat_id not in incoming_category_ids]
    deleted = len(goals_to_delete)
    for goal in goals_to_delete:
        await uow.goals.delete(goal)

    await uow.flush()

    logger.info(
        "bulk_upsert_goals_completed",
        family_id=str(family_id),
        year_month=year_month,
        created=created,
        updated=updated,
        deleted=deleted,
    )
    return {"created": created, "updated": updated, "deleted": deleted}
