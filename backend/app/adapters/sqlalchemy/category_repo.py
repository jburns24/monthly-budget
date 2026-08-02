"""SQLAlchemy implementation of :class:`~app.ports.repositories.category.CategoryRepository`."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.category import Category
from app.models.expense import Expense


class SqlAlchemyCategoryRepository:
    """Category reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_family(self, category_id: UUID, family_id: UUID) -> Category | None:
        result = await self._session.execute(
            select(Category).where(Category.id == category_id, Category.family_id == family_id)
        )
        return result.scalar_one_or_none()

    async def list_active(self, family_id: UUID) -> list[Category]:
        result = await self._session.execute(
            select(Category)
            .where(Category.family_id == family_id, Category.is_active.is_(True))
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        return list(result.scalars().all())

    async def list_names(self, family_id: UUID) -> set[str]:
        result = await self._session.execute(select(Category.name).where(Category.family_id == family_id))
        return set(result.scalars().all())

    async def first_active(self, family_id: UUID) -> Category | None:
        result = await self._session.execute(
            select(Category)
            .where(Category.family_id == family_id, Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
            .limit(1)
        )
        return result.scalar_one_or_none()

    def add(self, category: Category) -> None:
        self._session.add(category)

    def add_all(self, categories: Sequence[Category]) -> None:
        self._session.add_all(categories)

    async def delete(self, category: Category) -> None:
        await self._session.delete(category)

    # ------------------------------------------------------------------
    # Postgres tier
    # ------------------------------------------------------------------

    async def find_similar_active(self, family_id: UUID, term: str, threshold: float) -> Category | None:
        if not term:
            return None
        # pg_trgm. The expression appears twice, once to filter and once to rank,
        # and Postgres really does evaluate both — there is no common-subexpression
        # elimination between a qual and a sort key. Left as-is rather than hoisted
        # into a subquery: a family has a handful of categories, and this is
        # byte-for-byte the query category_suggestion._trgm_match runs today.
        similarity = func.similarity(Category.name, term)
        result = await self._session.execute(
            select(Category)
            .where(
                Category.family_id == family_id,
                Category.is_active.is_(True),
                similarity > threshold,
            )
            .order_by(similarity.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def most_used_since(self, family_id: UUID, cutoff: date) -> Category | None:
        result = await self._session.execute(
            select(Category)
            .join(Expense, Expense.category_id == Category.id)
            .where(
                Expense.family_id == family_id,
                Category.is_active.is_(True),
                Expense.expense_date >= cutoff,
            )
            .group_by(Category.id)
            .order_by(func.count().desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
