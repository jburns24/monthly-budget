"""In-memory stand-in for :class:`~app.ports.read_models.BudgetQuery`.

``category_spend_and_goals`` / ``month_totals`` / ``has_starting_balance`` are
Postgres tier — aggregates a fake would have to re-implement rather than test.
Matches the ``CategoryRepository`` precedent (``find_similar_active``,
``most_used_since``): raise rather than approximate.
"""

from uuid import UUID

from app.adapters.memory.store import MemoryStore, postgres_tier
from app.ports.read_models import CategorySpendRow


class MemoryBudgetQuery:
    """Stub over a :class:`~app.adapters.memory.store.MemoryStore`. Postgres tier only."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def category_spend_and_goals(self, family_id: UUID, year_month: str) -> list[CategorySpendRow]:
        postgres_tier(
            "BudgetQuery.category_spend_and_goals",
            "a 5-way SQL aggregate (LEFT JOIN + GROUP BY); the percentage/status/total "
            "math it feeds is unit-tested separately via expense_service.build_budget_summary",
        )

    async def month_totals(self, family_id: UUID, year_month: str) -> tuple[int, int]:
        postgres_tier(
            "BudgetQuery.month_totals",
            "a SUM FILTER aggregate over entry_type for family/month income vs spend",
        )

    async def has_starting_balance(self, family_id: UUID, year_month: str) -> bool:
        postgres_tier(
            "BudgetQuery.has_starting_balance",
            "a cheap EXISTS over is_starting_balance for the family/month",
        )
