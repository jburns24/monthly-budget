"""SQLAlchemy implementation of :class:`~app.ports.repositories.recurring_expense.RecurringExpenseRepository`."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_expense import RecurringExpense


class SqlAlchemyRecurringExpenseRepository:
    """RecurringExpense reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_family(self, family_id: UUID) -> list[RecurringExpense]:
        result = await self._session.execute(
            select(RecurringExpense)
            .where(RecurringExpense.family_id == family_id)
            .order_by(RecurringExpense.created_at.desc(), RecurringExpense.id)
        )
        return list(result.scalars().all())

    async def get_in_family(self, rule_id: UUID, family_id: UUID) -> RecurringExpense | None:
        result = await self._session.execute(
            select(RecurringExpense).where(RecurringExpense.id == rule_id, RecurringExpense.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def lock_due(self, family_id: UUID, today: date) -> list[RecurringExpense]:
        # populate_existing: a request that waited on the lock must see the winner's
        # advanced next_due_date, not a stale copy already in the identity map.
        result = await self._session.execute(
            select(RecurringExpense)
            .where(
                RecurringExpense.family_id == family_id,
                RecurringExpense.is_active.is_(True),
                RecurringExpense.next_due_date <= today,
            )
            .order_by(RecurringExpense.created_at, RecurringExpense.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    def add(self, rule: RecurringExpense) -> None:
        self._session.add(rule)

    async def delete(self, rule: RecurringExpense) -> None:
        await self._session.delete(rule)
