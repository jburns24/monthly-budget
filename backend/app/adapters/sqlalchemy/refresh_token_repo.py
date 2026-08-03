"""SQLAlchemy implementation of :class:`~app.ports.repositories.refresh_token.RefreshTokenRepository`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token_blacklist import RefreshTokenBlacklist


class SqlAlchemyRefreshTokenRepository:
    """Refresh-token blacklist reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_blacklisted(self, jti: str) -> bool:
        # Selects the primary key rather than the entity: the caller wants a
        # yes/no, and there is no reason to put a row the request will never
        # read into the session's identity map.
        found = await self._session.scalar(select(RefreshTokenBlacklist.id).where(RefreshTokenBlacklist.jti == jti))
        return found is not None

    def add(self, entry: RefreshTokenBlacklist) -> None:
        self._session.add(entry)
