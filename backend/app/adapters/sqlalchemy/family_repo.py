"""SQLAlchemy implementation of :class:`~app.ports.repositories.family.FamilyRepository`."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.family import Family
from app.models.family_member import FamilyMember


class SqlAlchemyFamilyRepository:
    """Family reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, family_id: UUID) -> Family | None:
        result = await self._session.execute(select(Family).where(Family.id == family_id))
        return result.scalar_one_or_none()

    async def get_with_members(self, family_id: UUID) -> Family | None:
        result = await self._session.execute(
            select(Family)
            .options(joinedload(Family.members).joinedload(FamilyMember.user))
            .where(Family.id == family_id)
        )
        # ``unique()`` is mandatory, not stylistic: joinedload against a
        # collection multiplies the Family row once per member, and SQLAlchemy
        # refuses to return the duplicated rows without it.
        return result.unique().scalar_one_or_none()

    def add(self, family: Family) -> None:
        self._session.add(family)
