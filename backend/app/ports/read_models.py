"""Read models: query ports that return plain DTOs instead of aggregates.

A repository hands back ORM instances you can mutate. A read model hands back
immutable rows shaped for one screen, and there is no write path. The budget
summary is the one query in this codebase where that distinction earns its keep:
it is a five-way aggregate with a scalar subquery, so the SQL has to stay in
Postgres, but the percentage/status/total arithmetic layered on top is pure and
belongs in a function unit-tested with literal rows.

``expense_service.get_budget_summary`` is the only consumer: it reads the rows
through this port and hands them to the pure ``build_budget_summary``.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CategorySpendRow:
    """One active category's spend and goal for a single month.

    ``goal_cents`` is None when the family set no goal for that category that
    month, which is different from a goal of zero and drives a different status.
    """

    category_id: UUID
    category_name: str
    icon: str | None
    spent_cents: int
    goal_cents: int | None


class BudgetQuery(Protocol):
    """Aggregate reads that back the budget summary screen."""

    async def category_spend_and_goals(self, family_id: UUID, year_month: str) -> list[CategorySpendRow]:
        """Return one row per active category, ordered by ``(sort_order, name)``.

        Postgres tier: LEFT JOIN against expenses plus a goals subquery, grouped
        per category. Category ``spent_cents`` sums only ``entry_type = 'expense'``.
        """
        ...

    async def month_totals(self, family_id: UUID, year_month: str) -> tuple[int, int]:
        """Return ``(income_cents, spent_cents)`` for the family/month.

        ``spent_cents`` sums ``entry_type = 'expense'`` only;
        ``income_cents`` sums ``entry_type = 'income'`` only.
        """
        ...

    async def has_starting_balance(self, family_id: UUID, year_month: str) -> bool:
        """True when a starting-balance income row exists for the family/month."""
        ...
