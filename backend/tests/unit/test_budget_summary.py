"""Unit tests for the pure ``build_budget_summary`` function. No database.

Design doc Step 5: ``expense_service.get_budget_summary`` was a 5-way SQL
aggregate with the percentage/status/total math bolted onto the same query.
Split apart, the SQL becomes ``BudgetQuery.category_spend_and_goals`` (Postgres
tier, see ``tests/test_sqlalchemy_adapter.py``), and this pure function is fed
literal :class:`~app.ports.read_models.CategorySpendRow` rows — no ORM, no
adapter, no event loop.
"""

import uuid

from app.ports.read_models import CategorySpendRow
from app.services.expense_service import build_budget_summary


def _row(
    *, spent_cents: int, goal_cents: int | None, name: str = "Groceries", icon: str | None = "cart"
) -> CategorySpendRow:
    return CategorySpendRow(
        category_id=uuid.uuid4(),
        category_name=name,
        icon=icon,
        spent_cents=spent_cents,
        goal_cents=goal_cents,
    )


def test_empty_rows_gives_a_zeroed_summary() -> None:
    summary = build_budget_summary([], "2026-04", is_editable=True)

    assert summary.year_month == "2026-04"
    assert summary.total_spent_cents == 0
    assert summary.total_income_cents == 0
    assert summary.has_starting_balance is False
    assert summary.categories == []
    assert summary.is_editable is True


def test_total_spent_cents_sums_every_category() -> None:
    rows = [_row(spent_cents=15000, goal_cents=60000), _row(spent_cents=2500, goal_cents=None, name="Transport")]

    summary = build_budget_summary(rows, "2026-04", is_editable=True)

    assert summary.total_spent_cents == 17500


def test_total_income_cents_is_passed_through_not_derived_from_category_rows() -> None:
    """Income is family-level (no category); category rows stay expense-only spend."""
    rows = [_row(spent_cents=15000, goal_cents=60000)]

    summary = build_budget_summary(
        rows,
        "2026-04",
        is_editable=True,
        total_income_cents=500000,
    )

    assert summary.total_spent_cents == 15000
    assert summary.total_income_cents == 500000


def test_has_starting_balance_defaults_false_and_passes_through() -> None:
    assert build_budget_summary([], "2026-04", is_editable=True).has_starting_balance is False
    assert build_budget_summary([], "2026-04", is_editable=True, has_starting_balance=True).has_starting_balance is True


def test_no_goal_gives_status_none_and_zero_percentage() -> None:
    (summary_row,) = build_budget_summary(
        [_row(spent_cents=2500, goal_cents=None)], "2026-04", is_editable=True
    ).categories

    assert summary_row.goal_cents is None
    assert summary_row.percentage == 0.0
    assert summary_row.status == "none"


def test_a_goal_of_zero_is_status_none_not_a_division_error() -> None:
    (summary_row,) = build_budget_summary([_row(spent_cents=100, goal_cents=0)], "2026-04", is_editable=True).categories

    assert summary_row.status == "none"
    assert summary_row.percentage == 0.0


def test_under_eighty_percent_is_green() -> None:
    (summary_row,) = build_budget_summary(
        [_row(spent_cents=100, goal_cents=1000)], "2026-04", is_editable=True
    ).categories

    assert summary_row.status == "green"
    assert summary_row.percentage == 0.1


def test_eighty_to_ninety_nine_percent_is_yellow() -> None:
    (summary_row,) = build_budget_summary(
        [_row(spent_cents=85000, goal_cents=100000)], "2026-04", is_editable=True
    ).categories

    assert summary_row.status == "yellow"
    assert summary_row.percentage == 0.85


def test_at_or_over_the_goal_is_red() -> None:
    (summary_row,) = build_budget_summary(
        [_row(spent_cents=100000, goal_cents=100000)], "2026-04", is_editable=True
    ).categories

    assert summary_row.status == "red"
    assert summary_row.percentage == 1.0


def test_over_the_goal_is_still_red() -> None:
    (summary_row,) = build_budget_summary(
        [_row(spent_cents=150000, goal_cents=100000)], "2026-04", is_editable=True
    ).categories

    assert summary_row.status == "red"
    assert summary_row.percentage == 1.5


def test_percentage_is_rounded_to_four_places() -> None:
    (summary_row,) = build_budget_summary([_row(spent_cents=1, goal_cents=3)], "2026-04", is_editable=True).categories

    assert summary_row.percentage == 0.3333


def test_row_fields_pass_through_unchanged() -> None:
    row = _row(spent_cents=500, goal_cents=1000, name="Dining", icon="fork")

    (summary_row,) = build_budget_summary([row], "2026-04", is_editable=True).categories

    assert summary_row.category_id == row.category_id
    assert summary_row.category_name == "Dining"
    assert summary_row.icon == "fork"
    assert summary_row.spent_cents == 500
    assert summary_row.goal_cents == 1000


def test_is_editable_passes_through() -> None:
    summary = build_budget_summary([], "2026-04", is_editable=False)

    assert summary.is_editable is False
