"""SQLAlchemy 2.0 async database engine, session factory, and declarative base."""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Hosted Supabase's Supavisor transaction pooler multiplexes many client
# connections onto few server connections *per transaction*, which is
# incompatible with asyncpg's default use of named prepared statements (the
# server-side name can outlive the transaction it was prepared in and collide
# across clients). See docs/data-layer-ports-design.md#connecting-to-hosted-supabase.
_SUPAVISOR_POOLER_HOST_MARKER = "pooler.supabase.com"
_SUPAVISOR_TRANSACTION_POOLER_PORT = 6543


def resolve_engine_kwargs(url: str) -> dict[str, Any]:
    """Return create_async_engine kwargs appropriate for the connection target.

    Hosted Supabase exposes three connection modes that need different engine
    settings; plain local Postgres is unaffected:

    - **Supavisor transaction pooler** (host contains ``pooler.supabase.com``,
      port 6543): Supavisor itself already pools connections, and its
      transaction mode rejects asyncpg's default named prepared statements.
      Disable statement caching and give every prepared statement a unique
      name, plus ``pool_pre_ping``/``pool_recycle`` since the pooler may
      silently drop idle connections.
    - **Supavisor session pooler** (port 5432 on a pooler host) and **direct
      connections**: behave like a normal Postgres connection pool.
    - **Plain local Postgres**: unchanged from today.
    """
    parsed = make_url(url)
    is_transaction_pooler = (
        parsed.host is not None
        and _SUPAVISOR_POOLER_HOST_MARKER in parsed.host
        and parsed.port == _SUPAVISOR_TRANSACTION_POOLER_PORT
    )
    if is_transaction_pooler:
        return {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "connect_args": {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
                "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
            },
        }
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }


# Create the async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    **resolve_engine_kwargs(settings.database_url),
)

# Create the async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


# Import models here so Alembic autogenerate detects them
import app.models  # noqa: E402, F401


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
