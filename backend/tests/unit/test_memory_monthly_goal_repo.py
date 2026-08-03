"""Unit tests for the in-memory MonthlyGoalRepository. No database."""

import uuid
from datetime import datetime

import pytest

from app.ports.errors import UniqueViolation
from tests.unit.conftest import make_category, make_monthly_goal, seed


async def test_flush_assigns_id_and_created_at(uow, family_id) -> None:
    """Postgres supplies id (Python default) and created_at (server_default); the fake must too."""
    category = make_category(family_id, "Groceries")
    await seed(uow, category)
    goal = make_monthly_goal(family_id, category.id, "2026-04")
    assert goal.id is None

    uow.goals.add(goal)
    await uow.flush()

    assert isinstance(goal.id, uuid.UUID)
    assert isinstance(goal.created_at, datetime)


async def test_queries_do_not_see_unflushed_writes(uow, family_id) -> None:
    """The real session runs with autoflush=False, so a staged add is invisible until flush."""
    category_id = uuid.uuid4()
    uow.goals.add(make_monthly_goal(family_id, category_id, "2026-04"))

    assert await uow.goals.list_for_month(family_id, "2026-04") == []

    await uow.flush()

    assert len(await uow.goals.list_for_month(family_id, "2026-04")) == 1


async def test_duplicate_family_category_month_raises_unique_violation(uow, family_id) -> None:
    """The fake enforces uq_monthly_goals_family_category_month."""
    category_id = uuid.uuid4()
    await seed(uow, make_monthly_goal(family_id, category_id, "2026-04"))
    uow.goals.add(make_monthly_goal(family_id, category_id, "2026-04"))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_monthly_goals_family_category_month"


async def test_same_category_month_in_a_different_family_is_allowed(uow, family_id) -> None:
    """The constraint is composite, not on (category_id, year_month) alone."""
    category_id = uuid.uuid4()
    other_family = uuid.uuid4()
    await seed(uow, make_monthly_goal(family_id, category_id, "2026-04"))

    uow.goals.add(make_monthly_goal(other_family, category_id, "2026-04"))
    await uow.flush()

    assert len(await uow.goals.list_for_month(other_family, "2026-04")) == 1


async def test_get_in_family_returns_the_goal(uow, family_id) -> None:
    """get_in_family finds a goal owned by the family."""
    goal = make_monthly_goal(family_id, uuid.uuid4(), "2026-04")
    await seed(uow, goal)

    found = await uow.goals.get_in_family(goal.id, family_id)

    assert found is not None
    assert found.id == goal.id


async def test_get_in_family_returns_none_for_another_familys_goal(uow, family_id) -> None:
    """get_in_family scopes by family_id."""
    goal = make_monthly_goal(family_id, uuid.uuid4(), "2026-04")
    await seed(uow, goal)

    assert await uow.goals.get_in_family(goal.id, uuid.uuid4()) is None


async def test_get_in_family_returns_none_for_an_unknown_id(uow, family_id) -> None:
    """A missing id is None, not an error."""
    assert await uow.goals.get_in_family(uuid.uuid4(), family_id) is None


async def test_list_for_month_is_scoped_to_family_and_month(uow, family_id) -> None:
    """list_for_month filters on both family_id and year_month."""
    other_family = uuid.uuid4()
    cat1, cat2 = uuid.uuid4(), uuid.uuid4()
    await seed(
        uow,
        make_monthly_goal(family_id, cat1, "2026-04"),
        make_monthly_goal(family_id, cat2, "2026-03"),
        make_monthly_goal(other_family, cat1, "2026-04"),
    )

    goals = await uow.goals.list_for_month(family_id, "2026-04")

    assert len(goals) == 1
    assert goals[0].category_id == cat1


async def test_latest_month_before_returns_the_most_recent_prior_month(uow, family_id) -> None:
    """latest_month_before is a string-comparison MAX, skipping gaps."""
    cat = uuid.uuid4()
    await seed(
        uow,
        make_monthly_goal(family_id, cat, "2026-01"),
        make_monthly_goal(uuid.uuid4(), cat, "2026-02"),
    )
    await seed(uow, make_monthly_goal(family_id, uuid.uuid4(), "2026-01"))

    result = await uow.goals.latest_month_before(family_id, "2026-04")

    assert result == "2026-01"


async def test_latest_month_before_ignores_months_on_or_after_the_target(uow, family_id) -> None:
    """Only months strictly before year_month count."""
    await seed(uow, make_monthly_goal(family_id, uuid.uuid4(), "2026-04"))

    assert await uow.goals.latest_month_before(family_id, "2026-04") is None


async def test_latest_month_before_returns_none_without_prior_goals(uow, family_id) -> None:
    """No goals at all means None, not an error."""
    assert await uow.goals.latest_month_before(family_id, "2026-04") is None


async def test_add_all_inserts_every_goal(uow, family_id) -> None:
    """add_all stages a whole batch for the next flush."""
    cat1, cat2 = uuid.uuid4(), uuid.uuid4()

    uow.goals.add_all(
        [
            make_monthly_goal(family_id, cat1, "2026-04", amount_cents=1000),
            make_monthly_goal(family_id, cat2, "2026-04", amount_cents=2000),
        ]
    )
    await uow.flush()

    assert len(await uow.goals.list_for_month(family_id, "2026-04")) == 2


async def test_delete_removes_the_row_on_flush(uow, family_id) -> None:
    """delete is staged, then applied by flush."""
    goal = make_monthly_goal(family_id, uuid.uuid4(), "2026-04")
    await seed(uow, goal)

    await uow.goals.delete(goal)
    assert len(await uow.goals.list_for_month(family_id, "2026-04")) == 1

    await uow.flush()

    assert await uow.goals.list_for_month(family_id, "2026-04") == []


async def test_mutating_a_returned_instance_is_tracked_without_an_explicit_add(uow, family_id) -> None:
    """Services rely on implicit dirty tracking: ``goal.amount_cents = x; await flush()``."""
    goal = make_monthly_goal(family_id, uuid.uuid4(), "2026-04", amount_cents=5000)
    await seed(uow, goal)
    (fetched,) = await uow.goals.list_for_month(family_id, "2026-04")

    fetched.amount_cents = 9999
    fetched.version = fetched.version + 1
    await uow.flush()

    (persisted,) = await uow.goals.list_for_month(family_id, "2026-04")
    assert persisted.amount_cents == 9999
    assert persisted.version == 2
