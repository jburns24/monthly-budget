"""Unit tests for monthly_goal_service against the in-memory adapter. No database.

The equivalent Postgres-tier coverage lives in ``tests/test_monthly_goals_service.py``
and ``tests/test_monthly_goals_api.py``. This aggregate has the densest business
logic in the codebase — rollover, optimistic version, bulk upsert diffing — so it
is the best return on the fake: every branch of ``bulk_upsert_goals`` and the
duplicate-key race in ``copy_goals_from_previous_month`` are exercised here with
no connection.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.services.monthly_goal_service import (
    bulk_upsert_goals,
    copy_goals_from_previous_month,
    create_goal,
    delete_goal,
    get_or_check_previous_goals,
    get_previous_month,
    list_goals,
    update_goal,
)
from tests.unit.conftest import make_category, make_monthly_goal, seed

# ---------------------------------------------------------------------------
# get_previous_month — pure function, no seam involved, smoke-tested here too
# ---------------------------------------------------------------------------


def test_get_previous_month_wraps_january_to_december() -> None:
    assert get_previous_month("2026-01") == "2025-12"


# ---------------------------------------------------------------------------
# get_or_check_previous_goals / list_goals
# ---------------------------------------------------------------------------


async def test_get_or_check_previous_goals_returns_goals_when_they_exist(uow, family_id) -> None:
    """Existing goals for the month short-circuit the rollover hint."""
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04")
    await seed(uow, goal)

    goals, has_previous = await get_or_check_previous_goals(uow, family_id, "2026-04")

    assert [g.id for g in goals] == [goal.id]
    assert has_previous is False


async def test_get_or_check_previous_goals_flags_a_prior_month(uow, family_id) -> None:
    """No goals this month, but a prior month has some — the frontend should offer rollover."""
    category = make_category(family_id, "Dining")
    await seed(uow, category)
    await seed(uow, make_monthly_goal(family_id, category.id, "2026-03"))

    goals, has_previous = await get_or_check_previous_goals(uow, family_id, "2026-04")

    assert goals == []
    assert has_previous is True


async def test_get_or_check_previous_goals_no_goals_anywhere(uow, family_id) -> None:
    """A brand-new family has no goals and no rollover hint."""
    goals, has_previous = await get_or_check_previous_goals(uow, family_id, "2026-04")

    assert goals == []
    assert has_previous is False


async def test_list_goals_isolates_by_family(uow, family_id) -> None:
    """list_goals never leaks another family's goals."""
    other_family = uuid.uuid4()
    category = make_category(other_family, "Bills")
    await seed(uow, category)
    await seed(uow, make_monthly_goal(other_family, category.id, "2026-03"))

    goals, has_previous = await list_goals(uow, family_id, "2026-04")

    assert goals == []
    assert has_previous is False


# ---------------------------------------------------------------------------
# create_goal
# ---------------------------------------------------------------------------


async def test_create_goal_returns_a_populated_goal(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)

    goal = await create_goal(uow, family_id, category.id, "2026-04", 50000)

    assert goal.family_id == family_id
    assert goal.category_id == category.id
    assert goal.year_month == "2026-04"
    assert goal.amount_cents == 50000
    assert goal.version == 1
    assert isinstance(goal.id, uuid.UUID)
    assert goal.created_at is not None


async def test_create_goal_raises_404_for_an_unknown_category(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_goal(uow, family_id, uuid.uuid4(), "2026-04", 50000)

    assert exc_info.value.status_code == 404


async def test_create_goal_raises_400_for_an_inactive_category(uow, family_id) -> None:
    category = make_category(family_id, "Archived", is_active=False)
    await seed(uow, category)

    with pytest.raises(HTTPException) as exc_info:
        await create_goal(uow, family_id, category.id, "2026-04", 50000)

    assert exc_info.value.status_code == 400


async def test_create_goal_rejects_a_duplicate_with_409(uow, family_id) -> None:
    """The unique constraint translation drives the 409 — no database needed."""
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    await seed(uow, make_monthly_goal(family_id, category.id, "2026-04"))

    with pytest.raises(HTTPException) as exc_info:
        await create_goal(uow, family_id, category.id, "2026-04", 60000)

    assert exc_info.value.status_code == 409


async def test_create_goal_rolls_the_request_back_on_a_duplicate(uow, family_id) -> None:
    """Risk (f): the 409 path discards the whole transaction, not just the failed insert."""
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    existing = make_monthly_goal(family_id, category.id, "2026-04", amount_cents=50000)
    await seed(uow, existing)

    with pytest.raises(HTTPException):
        await create_goal(uow, family_id, category.id, "2026-04", 60000)

    goals = await uow.goals.list_for_month(family_id, "2026-04")
    assert [g.amount_cents for g in goals] == [50000]


# ---------------------------------------------------------------------------
# update_goal
# ---------------------------------------------------------------------------


async def test_update_goal_increments_version_and_amount(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04", amount_cents=50000)
    await seed(uow, goal)

    updated = await update_goal(uow, goal.id, family_id, 75000, expected_version=1)

    assert updated.amount_cents == 75000
    assert updated.version == 2


async def test_update_goal_raises_404_for_an_unknown_goal(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_goal(uow, uuid.uuid4(), family_id, 75000, expected_version=1)

    assert exc_info.value.status_code == 404


async def test_update_goal_raises_404_for_another_familys_goal(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04")
    await seed(uow, goal)

    with pytest.raises(HTTPException) as exc_info:
        await update_goal(uow, goal.id, uuid.uuid4(), 75000, expected_version=1)

    assert exc_info.value.status_code == 404


async def test_update_goal_raises_409_on_a_version_mismatch(uow, family_id) -> None:
    """Optimistic locking: a stale expected_version is a conflict, not a write."""
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04", amount_cents=50000)
    await seed(uow, goal)

    with pytest.raises(HTTPException) as exc_info:
        await update_goal(uow, goal.id, family_id, 75000, expected_version=99)

    assert exc_info.value.status_code == 409
    persisted = await uow.goals.get_in_family(goal.id, family_id)
    assert persisted is not None
    assert persisted.amount_cents == 50000


# ---------------------------------------------------------------------------
# delete_goal
# ---------------------------------------------------------------------------


async def test_delete_goal_removes_it(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04")
    await seed(uow, goal)

    await delete_goal(uow, goal.id, family_id)

    assert await uow.goals.get_in_family(goal.id, family_id) is None


async def test_delete_goal_raises_404_for_an_unknown_goal(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await delete_goal(uow, uuid.uuid4(), family_id)

    assert exc_info.value.status_code == 404


async def test_delete_goal_raises_404_for_another_familys_goal(uow, family_id) -> None:
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04")
    await seed(uow, goal)

    with pytest.raises(HTTPException) as exc_info:
        await delete_goal(uow, goal.id, uuid.uuid4())

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# copy_goals_from_previous_month (rollover)
# ---------------------------------------------------------------------------


async def test_copy_goals_from_previous_month_copies_every_category(uow, family_id) -> None:
    cat1 = make_category(family_id, "Groceries")
    cat2 = make_category(family_id, "Dining")
    await seed(uow, cat1, cat2)
    await seed(
        uow,
        make_monthly_goal(family_id, cat1.id, "2026-03", amount_cents=50000),
        make_monthly_goal(family_id, cat2.id, "2026-03", amount_cents=30000),
    )

    copied = await copy_goals_from_previous_month(uow, family_id, "2026-04")

    assert copied == 2
    new_goals = await uow.goals.list_for_month(family_id, "2026-04")
    assert {g.amount_cents for g in new_goals} == {50000, 30000}
    assert all(g.version == 1 for g in new_goals)


async def test_copy_goals_from_previous_month_finds_the_most_recent_month_skipping_gaps(uow, family_id) -> None:
    cat = make_category(family_id, "Transport")
    await seed(uow, cat)
    await seed(uow, make_monthly_goal(family_id, cat.id, "2026-01", amount_cents=20000))

    copied = await copy_goals_from_previous_month(uow, family_id, "2026-04")

    assert copied == 1


async def test_copy_goals_from_previous_month_returns_zero_without_a_source(uow, family_id) -> None:
    assert await copy_goals_from_previous_month(uow, family_id, "2026-04") == 0


async def test_copy_goals_from_previous_month_resets_version_to_one(uow, family_id) -> None:
    cat = make_category(family_id, "Entertainment")
    await seed(uow, cat)
    source = make_monthly_goal(family_id, cat.id, "2026-03", version=5)
    await seed(uow, source)

    await copy_goals_from_previous_month(uow, family_id, "2026-04")

    (new_goal,) = await uow.goals.list_for_month(family_id, "2026-04")
    assert new_goal.version == 1


async def test_copy_goals_from_previous_month_isolates_by_family(uow, family_id) -> None:
    other_family = uuid.uuid4()
    cat = make_category(other_family, "Dining")
    await seed(uow, cat)
    await seed(uow, make_monthly_goal(other_family, cat.id, "2026-03", amount_cents=99000))

    copied = await copy_goals_from_previous_month(uow, family_id, "2026-04")

    assert copied == 0
    assert await uow.goals.list_for_month(family_id, "2026-04") == []


async def test_copy_goals_from_previous_month_race_condition_returns_the_existing_count(uow, family_id) -> None:
    """A concurrent copy already landed a goal for (family, category, target month).

    The bulk insert collides on ``uq_monthly_goals_family_category_month``, so
    ``uow.flush()`` raises UniqueViolation exactly as the SQLAlchemy adapter's
    translated IntegrityError would. The service must catch it, roll back (the
    whole request — risk (f)), and report the count already there instead of
    raising.
    """
    cat = make_category(family_id, "Transport")
    await seed(uow, cat)
    await seed(
        uow,
        make_monthly_goal(family_id, cat.id, "2026-03", amount_cents=30000),
        make_monthly_goal(family_id, cat.id, "2026-04", amount_cents=30000),
    )

    copied = await copy_goals_from_previous_month(uow, family_id, "2026-04")

    assert copied == 1
    goals = await uow.goals.list_for_month(family_id, "2026-04")
    assert len(goals) == 1


# ---------------------------------------------------------------------------
# bulk_upsert_goals — the densest logic in the codebase, entirely fake-testable
# ---------------------------------------------------------------------------


async def test_bulk_upsert_goals_creates_when_none_exist(uow, family_id) -> None:
    cat1 = make_category(family_id, "Groceries")
    cat2 = make_category(family_id, "Dining")
    await seed(uow, cat1, cat2)

    result = await bulk_upsert_goals(
        uow,
        family_id,
        "2026-04",
        [
            {"category_id": cat1.id, "amount_cents": 50000},
            {"category_id": cat2.id, "amount_cents": 30000},
        ],
    )

    assert result == {"created": 2, "updated": 0, "deleted": 0}
    assert len(await uow.goals.list_for_month(family_id, "2026-04")) == 2


async def test_bulk_upsert_goals_updates_and_bumps_version(uow, family_id) -> None:
    cat = make_category(family_id, "Groceries")
    await seed(uow, cat)
    existing = make_monthly_goal(family_id, cat.id, "2026-04", amount_cents=50000, version=3)
    await seed(uow, existing)

    result = await bulk_upsert_goals(uow, family_id, "2026-04", [{"category_id": cat.id, "amount_cents": 75000}])

    assert result == {"created": 0, "updated": 1, "deleted": 0}
    persisted = await uow.goals.get_in_family(existing.id, family_id)
    assert persisted is not None
    assert persisted.amount_cents == 75000
    assert persisted.version == 4


async def test_bulk_upsert_goals_deletes_omitted_categories(uow, family_id) -> None:
    cat1 = make_category(family_id, "Groceries")
    cat2 = make_category(family_id, "Dining")
    await seed(uow, cat1, cat2)
    kept = make_monthly_goal(family_id, cat1.id, "2026-04", amount_cents=50000)
    dropped = make_monthly_goal(family_id, cat2.id, "2026-04", amount_cents=30000)
    await seed(uow, kept, dropped)

    result = await bulk_upsert_goals(uow, family_id, "2026-04", [{"category_id": cat1.id, "amount_cents": 50000}])

    assert result == {"created": 0, "updated": 1, "deleted": 1}
    remaining = await uow.goals.list_for_month(family_id, "2026-04")
    assert [g.id for g in remaining] == [kept.id]


async def test_bulk_upsert_goals_empty_list_deletes_everything(uow, family_id) -> None:
    cat = make_category(family_id, "Groceries")
    await seed(uow, cat)
    await seed(uow, make_monthly_goal(family_id, cat.id, "2026-04"))

    result = await bulk_upsert_goals(uow, family_id, "2026-04", [])

    assert result == {"created": 0, "updated": 0, "deleted": 1}
    assert await uow.goals.list_for_month(family_id, "2026-04") == []


async def test_bulk_upsert_goals_does_a_single_category_create_update_and_delete_together(uow, family_id) -> None:
    """One call exercising every branch of the diff at once."""
    cat_created = make_category(family_id, "Entertainment")
    cat_updated = make_category(family_id, "Groceries")
    cat_deleted = make_category(family_id, "Dining")
    await seed(uow, cat_created, cat_updated, cat_deleted)
    to_update = make_monthly_goal(family_id, cat_updated.id, "2026-04", amount_cents=1000)
    to_delete = make_monthly_goal(family_id, cat_deleted.id, "2026-04", amount_cents=2000)
    await seed(uow, to_update, to_delete)

    result = await bulk_upsert_goals(
        uow,
        family_id,
        "2026-04",
        [
            {"category_id": cat_created.id, "amount_cents": 4000},
            {"category_id": cat_updated.id, "amount_cents": 5000},
        ],
    )

    assert result == {"created": 1, "updated": 1, "deleted": 1}
    by_category = {g.category_id: g for g in await uow.goals.list_for_month(family_id, "2026-04")}
    assert set(by_category) == {cat_created.id, cat_updated.id}
    assert by_category[cat_updated.id].amount_cents == 5000
    assert by_category[cat_updated.id].version == 2


async def test_bulk_upsert_goals_raises_404_for_an_unknown_category(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await bulk_upsert_goals(uow, family_id, "2026-04", [{"category_id": uuid.uuid4(), "amount_cents": 50000}])

    assert exc_info.value.status_code == 404


async def test_bulk_upsert_goals_raises_400_for_an_inactive_category(uow, family_id) -> None:
    cat = make_category(family_id, "Archived", is_active=False)
    await seed(uow, cat)

    with pytest.raises(HTTPException) as exc_info:
        await bulk_upsert_goals(uow, family_id, "2026-04", [{"category_id": cat.id, "amount_cents": 50000}])

    assert exc_info.value.status_code == 400


async def test_bulk_upsert_goals_validates_before_writing_anything(uow, family_id) -> None:
    """A bad category anywhere in the list fails the whole batch before any write."""
    cat = make_category(family_id, "Groceries")
    await seed(uow, cat)

    with pytest.raises(HTTPException):
        await bulk_upsert_goals(
            uow,
            family_id,
            "2026-04",
            [
                {"category_id": cat.id, "amount_cents": 50000},
                {"category_id": uuid.uuid4(), "amount_cents": 1000},
            ],
        )

    assert await uow.goals.list_for_month(family_id, "2026-04") == []


async def test_bulk_upsert_goals_isolates_by_family(uow, family_id) -> None:
    other_family = uuid.uuid4()
    other_cat = make_category(other_family, "Dining")
    cat = make_category(family_id, "Groceries")
    await seed(uow, other_cat, cat)
    other_goal = make_monthly_goal(other_family, other_cat.id, "2026-04", amount_cents=99999)
    await seed(uow, other_goal)

    result = await bulk_upsert_goals(uow, family_id, "2026-04", [{"category_id": cat.id, "amount_cents": 50000}])

    assert result == {"created": 1, "updated": 0, "deleted": 0}
    persisted_other = await uow.goals.get_in_family(other_goal.id, other_family)
    assert persisted_other is not None
    assert persisted_other.amount_cents == 99999
