"""Repository protocol for the Family aggregate."""

from typing import Protocol
from uuid import UUID

from app.models.family import Family


class FamilyRepository(Protocol):
    """Reads and writes for :class:`~app.models.family.Family`.

    Two reads, deliberately named apart. ``get`` is the plain row — enough for
    the ownership and grace-period checks. ``get_with_members`` additionally
    guarantees ``family.members`` and each ``member.user`` are populated,
    because ``app/routers/family.py:_family_to_response`` walks
    ``family.members[*].user.email``. Eager-loading strategy is part of the port
    contract (``docs/data-layer-ports-design.md`` risk (a)), so the in-memory
    adapter populates both hops explicitly rather than leaving them to a lazy
    load that has no session to run on.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one. Conformance is checked statically
    by ``app.adapters.conformance`` and at runtime by
    ``tests/unit/test_conformance.py``.
    """

    async def get(self, family_id: UUID) -> Family | None:
        """Return the family by primary key, or None if it does not exist."""
        ...

    async def get_with_members(self, family_id: UUID) -> Family | None:
        """Like :meth:`get`, but with ``.members`` and each member's ``.user`` loaded."""
        ...

    def add(self, family: Family) -> None:
        """Stage a new family. Not durable until ``UnitOfWork.flush``."""
        ...
