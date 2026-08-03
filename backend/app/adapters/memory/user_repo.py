"""In-memory implementation of :class:`~app.ports.repositories.user.UserRepository`."""

from uuid import UUID

from app.adapters.memory.store import MemoryStore
from app.models.user import User


class MemoryUserRepository:
    """User reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get(self, user_id: UUID) -> User | None:
        return self._store.get(User, user_id)

    async def get_by_google_id(self, google_id: str) -> User | None:
        return next((u for u in self._store.rows(User) if u.google_id == google_id), None)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._store.rows(User) if u.email == email), None)

    def add(self, user: User) -> None:
        self._store.add(user)
