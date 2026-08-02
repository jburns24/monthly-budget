"""In-memory stand-in for :class:`~app.ports.read_models.BudgetQuery`.

``category_spend_and_goals`` is Postgres tier — a 5-way aggregate (categories
LEFT JOIN expenses LEFT JOIN a goals subquery, GROUP BY) that a fake would have
to re-implement rather than test. Matches the ``CategoryRepository`` precedent
(``find_similar_active``, ``most_used_since``): raise rather than approximate.
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
