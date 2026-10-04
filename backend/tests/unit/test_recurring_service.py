"""Unit tests for recurring_service against the in-memory adapter. No database."""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.expense import Expense
from app.services.recurring_service import (
    create_rule,
    delete_rule,
    occurrence_date,
    reconcile,
    update_rule,
)
from tests.unit.conftest import make_category, make_user, seed

# ---------------------------------------------------------------------------
# occurrence_date — pure schedule math
# ---------------------------------------------------------------------------


def test_weekly_and_biweekly_step_by_days() -> None:
    assert occurrence_date(date(2026, 1, 1), "weekly", 3) == date(2026, 1, 22)
    assert occurrence_date(date(2026, 1, 1), "biweekly", 2) == date(2026, 1, 29)


def test_monthly_clamps_to_month_end_without_drifting() -> None:
    start = date(2026, 1, 31)
    assert occurrence_date(start, "monthly", 1) == date(2026, 2, 28)
    assert occurrence_date(start, "monthly", 2) == date(2026, 3, 31)  # back on the 31st
    assert occurrence_date(date(2028, 1, 31), "monthly", 1) == date(2028, 2, 29)  # leap year


def test_monthly_rolls_over_the_year() -> None:
    assert occurrence_date(date(2026, 11, 15), "monthly", 3) == date(2027, 2, 15)


def test_yearly_handles_leap_day() -> None:
    assert occurrence_date(date(2024, 2, 29), "yearly", 1) == date(2025, 2, 28)
    assert occurrence_date(date(2024, 2, 29), "yearly", 4) == date(2028, 2, 29)


def test_unknown_frequency_is_rejected() -> None:
    with pytest.raises(ValueError):
        occurrence_date(date(2026, 1, 1), "daily", 1)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _setup(uow, family_id):
    category = make_category(family_id, "Rent")
    user = make_user()
    await seed(uow, category, user)
    return category, user


async def _rule(uow, family_id, category, user, *, today, start, **overrides):
    kwargs = dict(
        category_id=category.id,
        amount_cents=150000,
        description="Rent",
        entry_type="expense",
        frequency="monthly",
        start_date=start,
        end_date=None,
        today=today,
    )
    kwargs.update(overrides)
    return await create_rule(uow, family_id, user.id, **kwargs)


def _generated(uow, rule) -> list[Expense]:
    rows = [e for e in uow.store.rows(Expense) if e.recurring_expense_id == rule.id]
    return sorted(rows, key=lambda e: e.expense_date)


# ---------------------------------------------------------------------------
# create_rule
# ---------------------------------------------------------------------------


async def test_create_rule_generates_nothing_for_a_future_start(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)

    rule = await _rule(uow, family_id, category, user, today=date(2026, 5, 1), start=date(2026, 6, 1))

    assert _generated(uow, rule) == []
    assert rule.next_due_date == date(2026, 6, 1)
    assert rule.is_active


async def test_create_rule_backfills_every_due_occurrence(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)

    rule = await _rule(uow, family_id, category, user, today=date(2026, 4, 15), start=date(2026, 1, 31))

    rows = _generated(uow, rule)
    assert [e.expense_date for e in rows] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert [e.year_month for e in rows] == ["2026-01", "2026-02", "2026-03"]
    assert all(e.amount_cents == 150000 and e.category_id == category.id for e in rows)
    assert all(e.user_id == user.id and e.entry_type == "expense" for e in rows)
    assert rule.next_due_date == date(2026, 4, 30)
    assert rule.occurrences_created == 3


async def test_create_rule_supports_recurring_income(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)

    rule = await create_rule(
        uow,
        family_id,
        user.id,
        category_id=None,
        amount_cents=300000,
        description="Paycheck",
        entry_type="income",
        frequency="biweekly",
        start_date=date(2026, 4, 3),
        end_date=None,
        today=date(2026, 4, 20),
    )

    rows = _generated(uow, rule)
    assert [e.expense_date for e in rows] == [date(2026, 4, 3), date(2026, 4, 17)]
    assert all(e.entry_type == "income" and e.category_id is None for e in rows)


async def test_create_rule_rejects_an_inactive_category(uow, family_id) -> None:
    category = make_category(family_id, "Old", is_active=False)
    user = make_user()
    await seed(uow, category, user)

    with pytest.raises(HTTPException) as exc:
        await _rule(uow, family_id, category, user, today=date(2026, 4, 1), start=date(2026, 4, 1))

    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


async def test_reconcile_is_idempotent(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 4, 1), start=date(2026, 4, 1))

    assert await reconcile(uow, family_id, date(2026, 4, 1)) == 0
    assert await reconcile(uow, family_id, date(2026, 4, 28)) == 0
    assert len(_generated(uow, rule)) == 1


async def test_reconcile_catches_up_after_time_passes(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 4, 1), start=date(2026, 4, 1))

    assert await reconcile(uow, family_id, date(2026, 7, 2)) == 3

    assert [e.expense_date for e in _generated(uow, rule)] == [
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
    ]


async def test_reconcile_stops_at_end_date_and_deactivates(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(
        uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1), end_date=date(2026, 3, 15)
    )

    await reconcile(uow, family_id, date(2026, 12, 1))

    assert [e.expense_date for e in _generated(uow, rule)] == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    assert rule.is_active is False


async def test_reconcile_only_touches_the_given_family(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1))

    assert await reconcile(uow, uuid.uuid4(), date(2026, 6, 1)) == 0
    assert len(_generated(uow, rule)) == 1


async def test_reconcile_leaves_a_rule_due_when_its_category_is_archived(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1))
    category.is_active = False
    await uow.flush()

    assert await reconcile(uow, family_id, date(2026, 6, 1)) == 0
    assert rule.next_due_date == date(2026, 2, 1)

    category.is_active = True
    await uow.flush()
    assert await reconcile(uow, family_id, date(2026, 3, 1)) == 2


# ---------------------------------------------------------------------------
# update_rule / delete_rule
# ---------------------------------------------------------------------------


async def test_update_changes_future_entries_not_past_ones(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1))

    await update_rule(uow, family_id, rule.id, fields={"amount_cents": 160000}, today=date(2026, 2, 1))

    rows = _generated(uow, rule)
    assert [e.amount_cents for e in rows] == [150000, 160000]


async def test_pause_stops_generation_and_resume_skips_the_gap(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1))

    await update_rule(uow, family_id, rule.id, fields={"is_active": False}, today=date(2026, 1, 10))
    assert await reconcile(uow, family_id, date(2026, 5, 1)) == 0

    await update_rule(uow, family_id, rule.id, fields={"is_active": True}, today=date(2026, 5, 10))

    assert [e.expense_date for e in _generated(uow, rule)] == [date(2026, 1, 1)]
    assert rule.next_due_date == date(2026, 6, 1)


async def test_changing_frequency_re_anchors_on_the_next_due_date(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1))

    await update_rule(uow, family_id, rule.id, fields={"frequency": "weekly"}, today=date(2026, 1, 1))

    assert rule.start_date == date(2026, 2, 1)
    assert rule.next_due_date == date(2026, 2, 1)
    await reconcile(uow, family_id, date(2026, 2, 15))
    assert [e.expense_date for e in _generated(uow, rule)][1:] == [
        date(2026, 2, 1),
        date(2026, 2, 8),
        date(2026, 2, 15),
    ]


async def test_end_date_can_be_cleared(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(
        uow, family_id, category, user, today=date(2026, 1, 1), start=date(2026, 1, 1), end_date=date(2026, 6, 1)
    )

    await update_rule(uow, family_id, rule.id, fields={"end_date": None}, today=date(2026, 1, 1))

    assert rule.end_date is None


async def test_update_unknown_rule_is_404(uow, family_id) -> None:
    with pytest.raises(HTTPException) as exc:
        await update_rule(uow, family_id, uuid.uuid4(), fields={"amount_cents": 1}, today=date(2026, 1, 1))

    assert exc.value.status_code == 404


async def test_delete_keeps_generated_entries_and_stops_future_ones(uow, family_id) -> None:
    category, user = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, category, user, today=date(2026, 2, 1), start=date(2026, 1, 1))

    await delete_rule(uow, family_id, rule.id)

    assert len([e for e in uow.store.rows(Expense) if e.recurring_expense_id == rule.id]) == 2
    assert await reconcile(uow, family_id, date(2026, 9, 1)) == 0
