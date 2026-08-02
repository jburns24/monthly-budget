"""Repository protocol for the FamilyMember aggregate."""

from typing import Protocol
from uuid import UUID

from app.models.family_member import FamilyMember


class FamilyMemberRepository(Protocol):
    """Reads and writes for :class:`~app.models.family_member.FamilyMember`.

    ``get_with_family`` and ``get_with_user`` exist because two routers used to
    call ``await db.refresh(obj, ["family"|"user"])`` after fetching a plain
    membership row (``app/routers/users.py`` and ``app/routers/family.py``).
    Eager-loading strategy is part of the port contract — see
    ``docs/data-layer-ports-design.md`` risk (a) — so the memory adapter must
    populate ``.family`` / ``.user`` explicitly rather than relying on lazy
    relationship loading, which would blow up with ``MissingGreenlet`` outside
    a real session anyway.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one. Conformance is checked
    statically by ``app.adapters.conformance`` and at runtime by
    ``tests/unit/test_conformance.py``.
    """

    async def get_for_user_in_family(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        """Return the membership row for ``user_id`` in ``family_id``, or None."""
        ...

    async def get_any_for_user(self, user_id: UUID) -> FamilyMember | None:
        """Return ``user_id``'s membership in whatever family it belongs to, or None.

        Every user belongs to at most one family, so this never needs a
        ``family_id`` to disambiguate.
        """
        ...

    async def get_with_family(self, user_id: UUID) -> FamilyMember | None:
        """Like :meth:`get_any_for_user`, but with ``.family`` eager-loaded."""
        ...

    async def get_with_user(self, family_id: UUID, user_id: UUID) -> FamilyMember | None:
        """Like :meth:`get_for_user_in_family`, but with ``.user`` eager-loaded."""
        ...

    async def count_admins(self, family_id: UUID) -> int:
        """Return how many admins ``family_id`` has.

        Backs the "cannot remove/demote the last admin" guards.
        """
        ...

    def add(self, member: FamilyMember) -> None:
        """Stage a new membership. Not durable until ``UnitOfWork.flush``."""
        ...

    async def delete(self, member: FamilyMember) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...
