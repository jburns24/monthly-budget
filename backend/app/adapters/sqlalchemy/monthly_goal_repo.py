"""SQLAlchemy implementation of :class:`~app.ports.repositories.monthly_goal.MonthlyGoalRepository`."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monthly_goal import MonthlyGoal


class SqlAlchemyMonthlyGoalRepository:
    """MonthlyGoal reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_month(self, family_id: UUID, year_month: str) -> list[MonthlyGoal]:
        result = await self._session.execute(
            select(MonthlyGoal).where(
                MonthlyGoal.family_id == family_id,
                MonthlyGoal.year_month == year_month,
            )
        )
        return list(result.scalars().all())

    async def get_in_family(self, goal_id: UUID, family_id: UUID) -> MonthlyGoal | None:
        result = await self._session.execute(
            select(MonthlyGoal).where(MonthlyGoal.id == goal_id, MonthlyGoal.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def latest_month_before(self, family_id: UUID, year_month: str) -> str | None:
        result = await self._session.execute(
            select(MonthlyGoal.year_month)
            .where(MonthlyGoal.family_id == family_id, MonthlyGoal.year_month < year_month)
            .order_by(MonthlyGoal.year_month.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def add(self, goal: MonthlyGoal) -> None:
        self._session.add(goal)

    def add_all(self, goals: Sequence[MonthlyGoal]) -> None:
        self._session.add_all(goals)

    async def delete(self, goal: MonthlyGoal) -> None:
        await self._session.delete(goal)
