"""In-memory implementation of :class:`~app.ports.repositories.family_member.FamilyMemberRepository`."""

from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.user import User


class MemoryFamilyMemberRepository:
    """FamilyMember reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get_for_user_in_family(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        return next(
            (m for m in self._store.rows(FamilyMember) if m.family_id == family_id and m.user_id == user_id),
            None,
        )

    async def get_any_for_user(self, user_id: UUID) -> FamilyMember | None:
        return next((m for m in self._store.rows(FamilyMember) if m.user_id == user_id), None)

    async def get_with_family(self, user_id: UUID) -> FamilyMember | None:
        member = await self.get_any_for_user(user_id)
        if member is None:
            return None
        member.family = self._store.get(Family, member.family_id)
        return member

    async def get_with_user(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        member = await self.get_for_user_in_family(family_id, user_id)
        if member is None:
            return None
        member.user = self._store.get(User, member.user_id)
        return member

    async def count_admins(self, family_id: UUID) -> int:
        return sum(1 for m in self._store.rows(FamilyMember) if m.family_id == family_id and m.role == "admin")

    def add(self, member: FamilyMember) -> None:
        self._store.add(member)

    async def delete(self, member: FamilyMember) -> None:
        self._store.delete(member)
