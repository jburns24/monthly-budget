"""Wiring for the house price index refresh: the real downloader, sessions and advisory lock."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.database import AsyncSessionLocal, engine
from app.ports.unit_of_work import UnitOfWork
from app.services.hpi_fetcher import HttpxHpiFetcher
from app.services.hpi_service import HpiRefresher

# Arbitrary constant naming the refresh's cross-worker lock (pg_try_advisory_lock takes a bigint).
HPI_REFRESH_LOCK_KEY = 7_240_317_001


@asynccontextmanager
async def pg_advisory_lock(key: int = HPI_REFRESH_LOCK_KEY) -> AsyncIterator[bool]:
    """Try to take a Postgres advisory lock on a connection of its own; yields whether it was acquired.

    Session-level, so the lock survives the commits the refresh makes in between, and it is released
    when the block ends (or the connection dies). Held on a dedicated autocommit connection because a
    pooled one could be handed to another task mid-refresh.
    """
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        acquired = bool((await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


@asynccontextmanager
async def committing_uow() -> AsyncIterator[UnitOfWork]:
    """A unit of work on a fresh session that commits when the block exits cleanly."""
    async with AsyncSessionLocal() as session:
        uow = SqlAlchemyUnitOfWork(session, owns_transaction=True)
        try:
            yield uow
            await uow.commit()
        except BaseException:
            await uow.rollback()
            raise


def get_hpi_refresher() -> HpiRefresher:
    """FastAPI dependency: the production refresher. Tests override it with a fake fetcher."""
    return HpiRefresher(HttpxHpiFetcher(), committing_uow, pg_advisory_lock)
