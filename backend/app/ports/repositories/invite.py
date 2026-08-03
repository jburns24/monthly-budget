"""Repository protocol for the Invite aggregate."""

from typing import Protocol
from uuid import UUID

from app.models.invite import Invite


class InviteRepository(Protocol):
    """Reads and writes for :class:`~app.models.invite.Invite`.

    Every read here filters on ``status == 'pending'``, so the filter lives in
    the method names rather than in a parameter: an invite that has already been
    accepted or declined is never a legitimate target for any of these call
    sites, and folding the predicate into the port keeps three services from
    each having to remember it.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one. Conformance is checked statically
    by ``app.adapters.conformance`` and at runtime by
    ``tests/unit/test_conformance.py``.
    """

    async def get_pending(self, invite_id: UUID, user_id: UUID) -> Invite | None:
        """Return ``user_id``'s pending invite with this id, or None.

        Scoping by recipient inside the query is what makes "not yours",
        "already answered" and "does not exist" indistinguishable to the caller,
        which is the 404 the invite-response endpoint is specified to return.
        """
        ...

    async def get_pending_for(self, family_id: UUID, user_id: UUID) -> Invite | None:
        """Return ``user_id``'s pending invite to ``family_id``, or None.

        Backs the privacy-preserving duplicate check in ``invite_user``.
        """
        ...

    async def list_pending_for_user_detailed(self, user_id: UUID) -> list[Invite]:
        """Return every pending invite for ``user_id``, with ``.family`` and ``.inviting_user``.

        ``detailed`` is the eager-loading promise: ``GET /api/invites`` reads
        ``invite.family.name`` and ``invite.inviting_user.display_name``. See
        ``docs/data-layer-ports-design.md`` risk (a).
        """
        ...

    def add(self, invite: Invite) -> None:
        """Stage a new invite. Not durable until ``UnitOfWork.flush``."""
        ...
