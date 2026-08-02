"""In-memory implementation of :class:`~app.ports.repositories.monthly_goal.MonthlyGoalRepository`."""

from collections.abc import Sequence
from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.monthly_goal import MonthlyGoal


class MemoryMonthlyGoalRepository:
    """MonthlyGoal reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def list_for_month(self, family_id: UUID, year_month: str) -> list[MonthlyGoal]:
        return [g for g in self._store.rows(MonthlyGoal) if g.family_id == family_id and g.year_month == year_month]

    async def get_in_family(self, goal_id: UUID, family_id: UUID) -> MonthlyGoal | None:
        goal = self._store.get(MonthlyGoal, goal_id)
        if goal is None or goal.family_id != family_id:
            return None
        return goal

    async def latest_month_before(self, family_id: UUID, year_month: str) -> str | None:
        months = {
            g.year_month
            for g in self._store.rows(MonthlyGoal)
            if g.family_id == family_id and g.year_month < year_month
        }
        return max(months) if months else None

    def add(self, goal: MonthlyGoal) -> None:
        self._store.add(goal)

    def add_all(self, goals: Sequence[MonthlyGoal]) -> None:
        self._store.add_all(goals)

    async def delete(self, goal: MonthlyGoal) -> None:
        self._store.delete(goal)
