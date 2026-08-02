"""In-memory implementation of :class:`~app.ports.repositories.family.FamilyRepository`.

Risk (a): ``get_with_members`` has to build ``family.members`` from the store's
FamilyMember rows and hang a ``User`` off each one. Under the real ORM that is
``joinedload(members).joinedload(user)``; here there is no session to lazy-load
from, so an unpopulated collection would just be an empty list and
``_family_to_response`` would silently return a family with no members instead
of raising ``MissingGreenlet`` the way a router would against Postgres.
"""

from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.user import User


class MemoryFamilyRepository:
    """Family reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get(self, family_id: UUID) -> Family | None:
        return self._store.get(Family, family_id)

    async def get_with_members(self, family_id: UUID) -> Family | None:
        family = self._store.get(Family, family_id)
        if family is None:
            return None
        members = [m for m in self._store.rows(FamilyMember) if m.family_id == family_id]
        for member in members:
            member.user = self._store.get(User, member.user_id)
        family.members = members
        return family

    def add(self, family: Family) -> None:
        self._store.add(family)
