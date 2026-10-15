"""Wiring for the house price index refresh: the real downloader, sessions and advisory lock."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.database import AsyncSessionLocal, engine
from app.ports.unit_of_work import UnitOfWork
from app.services.hpi_fetcher import HttpxHpiFetcher
from app.services.hpi_service import HpiRefresher

# Arbitrary constant naming the refresh's cross-worker lock (pg_try_advisory_xact_lock takes a bigint).
HPI_REFRESH_LOCK_KEY = 7_240_317_001


@asynccontextmanager
async def pg_advisory_lock(key: int = HPI_REFRESH_LOCK_KEY) -> AsyncIterator[bool]:
    """Try to take a Postgres advisory lock on a connection of its own; yields whether it was acquired.

    Transaction-scoped (``pg_try_advisory_xact_lock``), not session-scoped: behind a transaction pooler
    (Supabase Supavisor, port 6543) the server connection can change between statements, so a session
    lock could leak or be unlocked from another backend. Inside an explicit transaction the pooler pins
    one server connection, so the lock holds, and it is released by the transaction ending (commit,
    rollback or a dead connection), with no unlock call to get wrong.

    The lock lives on a dedicated connection that does nothing else: it sits idle in transaction for the
    whole refresh, while the refresh itself runs on its own sessions (which commit independently).
    """
    async with engine.connect() as connection:
        async with connection.begin():
            acquired = bool(
                (await connection.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})).scalar()
            )
            yield acquired


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
