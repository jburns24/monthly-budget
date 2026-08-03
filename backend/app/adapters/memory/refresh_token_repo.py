"""In-memory implementation of :class:`~app.ports.repositories.refresh_token.RefreshTokenRepository`."""

from app.adapters.memory.store import MemoryStore
from app.models.refresh_token_blacklist import RefreshTokenBlacklist


class MemoryRefreshTokenRepository:
    """Blacklist reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`.

    Nothing here is Postgres tier: a jti lookup is an equality scan and the
    uniqueness of ``jti`` comes from the mapper, so the fake enforces it without
    being told.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def is_blacklisted(self, jti: str) -> bool:
        return any(entry.jti == jti for entry in self._store.rows(RefreshTokenBlacklist))

    def add(self, entry: RefreshTokenBlacklist) -> None:
        self._store.add(entry)
