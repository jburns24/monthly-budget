"""SQLAlchemy implementation of :class:`~app.ports.repositories.expense.ExpenseRepository`."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.expense import Expense

_EAGER = (selectinload(Expense.category), selectinload(Expense.user), selectinload(Expense.receipt))


def _month_filters(
    family_id: UUID,
    year_month: str,
    category_id: UUID | None,
    entry_type: str | None = None,
) -> list[Any]:
    filters: list[Any] = [Expense.family_id == family_id, Expense.year_month == year_month]
    if category_id is not None:
        filters.append(Expense.category_id == category_id)
    if entry_type is not None:
        filters.append(Expense.entry_type == entry_type)
    return filters


class SqlAlchemyExpenseRepository:
    """Expense reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_family(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        result = await self._session.execute(
            select(Expense).where(Expense.id == expense_id, Expense.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def get_in_family_with_details(self, expense_id: UUID, family_id: UUID) -> Expense | None:
        result = await self._session.execute(
            select(Expense).options(*_EAGER).where(Expense.id == expense_id, Expense.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def list_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        limit: int,
        offset: int,
        entry_type: str | None = None,
    ) -> list[Expense]:
        result = await self._session.execute(
            select(Expense)
            .options(*_EAGER)
            .where(*_month_filters(family_id, year_month, category_id, entry_type))
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_for_month(
        self,
        family_id: UUID,
        year_month: str,
        category_id: UUID | None,
        entry_type: str | None = None,
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Expense)
            .where(*_month_filters(family_id, year_month, category_id, entry_type))
        )
        return result.scalar_one()

    async def count_by_category(self, category_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Expense).where(Expense.category_id == category_id)
        )
        return result.scalar_one()

    def add(self, expense: Expense) -> None:
        self._session.add(expense)

    async def delete(self, expense: Expense) -> None:
        await self._session.delete(expense)
