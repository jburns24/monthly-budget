"""Repository protocol for the refresh-token blacklist."""

from typing import Protocol

from app.models.refresh_token_blacklist import RefreshTokenBlacklist


class RefreshTokenRepository(Protocol):
    """Reads and writes for :class:`~app.models.refresh_token_blacklist.RefreshTokenBlacklist`.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one, and lets a service narrow to just
    the methods it uses. Conformance is checked statically by
    ``app.adapters.conformance`` (and, because mypy is not yet wired into CI,
    also at runtime by ``tests/unit/test_conformance.py``).

    Two methods, because ``app/routers/auth.py`` only ever asks two questions:
    is this jti revoked, and revoke this jti. There is no ``get`` — nothing reads
    the row back — and no expiry sweep, because nothing prunes the table today.
    Adding either here would be inventing a contract no caller has.

    Not an aggregate the rest of the seam knows about: no service takes this
    repository. It exists so the auth router can stop holding an ``AsyncSession``
    (design doc Step 7.5), which is what unblocks Step 8.
    """

    async def is_blacklisted(self, jti: str) -> bool:
        """Return True if this refresh-token id has been revoked.

        Existence only — ``expires_at`` is deliberately not consulted. The caller
        has already decoded the token, so an expired one was rejected by the JWT
        library before it got here; filtering on expiry would only create a
        window where a revoked-but-expired jti reads as usable.
        """
        ...

    def add(self, entry: RefreshTokenBlacklist) -> None:
        """Stage a revocation. Not durable until ``UnitOfWork.flush``."""
        ...
