"""SQLAlchemy implementation of :class:`~app.ports.repositories.family_member.FamilyMemberRepository`."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.family_member import FamilyMember


class SqlAlchemyFamilyMemberRepository:
    """FamilyMember reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user_in_family(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        result = await self._session.execute(
            select(FamilyMember).where(FamilyMember.family_id == family_id, FamilyMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_any_for_user(self, user_id: UUID) -> FamilyMember | None:
        result = await self._session.execute(select(FamilyMember).where(FamilyMember.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_with_family(self, user_id: UUID) -> FamilyMember | None:
        result = await self._session.execute(
            select(FamilyMember).options(joinedload(FamilyMember.family)).where(FamilyMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_with_user(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        result = await self._session.execute(
            select(FamilyMember)
            .options(joinedload(FamilyMember.user))
            .where(FamilyMember.family_id == family_id, FamilyMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_admins(self, family_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(FamilyMember)
            .where(FamilyMember.family_id == family_id, FamilyMember.role == "admin")
        )
        return result.scalar_one()

    def add(self, member: FamilyMember) -> None:
        self._session.add(member)

    async def delete(self, member: FamilyMember) -> None:
        await self._session.delete(member)
