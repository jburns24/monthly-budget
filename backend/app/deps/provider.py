"""Wiring: build the production adapters for a request.

``get_uow`` is layered over the existing ``get_db`` rather than opening its own
session, and that is the whole coexistence strategy. FastAPI caches
``Depends(get_db)`` per request, so a router that takes both ``uow`` and ``db``
gets one session and one transaction, and every service still on ``get_db``
keeps working untouched.

It also means the test suite needs no new plumbing: an existing
``app.dependency_overrides[get_db] = override_get_db(db_session)`` propagates
through ``get_uow`` automatically, because the override replaces the dependency
``get_uow`` itself depends on.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.database import get_db


async def get_uow(session: AsyncSession = Depends(get_db)) -> SqlAlchemyUnitOfWork:
    """Return a UnitOfWork over this request's session.

    ``owns_transaction=True``: ``commit()`` really commits. Routers must not call
    it — ``get_db``'s teardown owns the request commit, exactly as it does today.
    """
    return SqlAlchemyUnitOfWork(session, owns_transaction=True)
