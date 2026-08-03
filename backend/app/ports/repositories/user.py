"""Repository protocol for the User aggregate."""

from typing import Protocol
from uuid import UUID

from app.models.user import User


class UserRepository(Protocol):
    """Reads and writes for :class:`~app.models.user.User`.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one, and lets a service narrow to just
    the methods it uses. Conformance is checked statically by
    ``app.adapters.conformance`` (and, because mypy is not yet wired into CI,
    also at runtime by ``tests/unit/test_conformance.py``).

    Do not add ``@runtime_checkable``: it only compares method *names*, which
    would give false confidence rather than none.
    """

    async def get(self, user_id: UUID) -> User | None:
        """Return the user by primary key, or None if it does not exist."""
        ...

    async def get_by_google_id(self, google_id: str) -> User | None:
        """Return the user with this Google OAuth subject id, or None."""
        ...

    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email address, or None."""
        ...

    def add(self, user: User) -> None:
        """Stage a new user. Not durable until ``UnitOfWork.flush``."""
        ...
