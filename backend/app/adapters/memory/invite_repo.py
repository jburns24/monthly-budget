"""In-memory implementation of :class:`~app.ports.repositories.invite.InviteRepository`.

Risk (a): ``list_pending_for_user_detailed`` must populate ``.family`` and
``.inviting_user`` itself, because ``GET /api/invites`` reads through both and
there is no session here to lazy-load them from.
"""

from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.family import Family
from app.models.invite import Invite
from app.models.user import User


class MemoryInviteRepository:
    """Invite reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def _pending(self) -> list[Invite]:
        return [i for i in self._store.rows(Invite) if i.status == "pending"]

    async def get_pending(self, invite_id: UUID, user_id: UUID) -> Invite | None:
        return next((i for i in self._pending() if i.id == invite_id and i.invited_user_id == user_id), None)

    async def get_pending_for(self, family_id: UUID, user_id: UUID) -> Invite | None:
        return next((i for i in self._pending() if i.family_id == family_id and i.invited_user_id == user_id), None)

    async def list_pending_for_user_detailed(self, user_id: UUID) -> list[Invite]:
        invites = [i for i in self._pending() if i.invited_user_id == user_id]
        for invite in invites:
            invite.family = self._store.get(Family, invite.family_id)
            invite.inviting_user = self._store.get(User, invite.invited_by)
        return invites

    def add(self, invite: Invite) -> None:
        self._store.add(invite)
