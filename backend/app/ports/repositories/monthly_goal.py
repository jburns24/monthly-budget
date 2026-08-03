"""Repository protocol for the MonthlyGoal aggregate."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.models.monthly_goal import MonthlyGoal


class MonthlyGoalRepository(Protocol):
    """Reads and writes for :class:`~app.models.monthly_goal.MonthlyGoal`."""

    async def list_for_month(self, family_id: UUID, year_month: str) -> list[MonthlyGoal]:
        """Return every goal for ``family_id`` in ``year_month``."""
        ...

    async def get_in_family(self, goal_id: UUID, family_id: UUID) -> MonthlyGoal | None:
        """Return the goal if it exists *and* belongs to ``family_id``, else None."""
        ...

    async def latest_month_before(self, family_id: UUID, year_month: str) -> str | None:
        """Return the most recent ``year_month`` with goals, strictly before ``year_month``.

        A plain string-comparison ``MAX`` — "YYYY-MM" sorts lexicographically the
        same as it sorts chronologically — so this is honestly fake-able, unlike
        the ranking queries on ``CategoryRepository``.
        """
        ...

    def add(self, goal: MonthlyGoal) -> None:
        """Stage a new goal. Not durable until ``UnitOfWork.flush``."""
        ...

    def add_all(self, goals: Sequence[MonthlyGoal]) -> None:
        """Stage a batch of new goals."""
        ...

    async def delete(self, goal: MonthlyGoal) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...
