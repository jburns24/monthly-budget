"""SQLAlchemy implementation of :class:`~app.ports.repositories.invite.InviteRepository`."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.invite import Invite


class SqlAlchemyInviteRepository:
    """Invite reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_pending(self, invite_id: UUID, user_id: UUID) -> Invite | None:
        result = await self._session.execute(
            select(Invite).where(
                Invite.id == invite_id,
                Invite.invited_user_id == user_id,
                Invite.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_for(self, family_id: UUID, user_id: UUID) -> Invite | None:
        result = await self._session.execute(
            select(Invite).where(
                Invite.family_id == family_id,
                Invite.invited_user_id == user_id,
                Invite.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_for_user_detailed(self, user_id: UUID) -> list[Invite]:
        result = await self._session.execute(
            select(Invite)
            .options(joinedload(Invite.family), joinedload(Invite.inviting_user))
            .where(Invite.invited_user_id == user_id, Invite.status == "pending")
        )
        return list(result.unique().scalars().all())

    def add(self, invite: Invite) -> None:
        self._session.add(invite)
