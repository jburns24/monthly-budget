"""Postgres-tier tests for the asset and house-price-index repositories."""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.config import settings
from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback for isolation."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def empty_house_price_index(db_session: AsyncSession) -> None:
    """The dev database may hold a real FHFA import; start each test from an empty index (rolled back at teardown)."""
    await db_session.execute(delete(HousePriceIndex))
    await db_session.execute(delete(HpiRefreshStatus))


@pytest.fixture
def uow(db_session: AsyncSession) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db_session, owns_transaction=False)


def _data(geo: str, year: int, quarter: int, value: str = "100.00") -> dict:
    return {"geo_code": geo, "year": year, "quarter": quarter, "index_value": Decimal(value)}


async def _count(db: AsyncSession, series: str) -> int:
    result = await db.execute(select(func.count()).select_from(HousePriceIndex).where(HousePriceIndex.series == series))
    return result.scalar_one()


async def test_replace_series_swaps_rows_in_bulk_and_leaves_other_series(uow, db_session) -> None:
    await uow.hpi.replace_series("state", [_data("NC", 2020, 1, "200.00")])
    await uow.hpi.replace_series("zip3", [_data("010", 2020, 1), _data("999", 2020, 1)])

    # More rows than one insert chunk, including a key that already exists.
    fresh = [_data(f"{n % 1000:03d}", 2000 + n // 4000, n % 4 + 1, "123.45") for n in range(11_000)]
    fresh = list({(r["geo_code"], r["year"], r["quarter"]): r for r in fresh}.values())
    await uow.hpi.replace_series("zip3", fresh)

    assert await _count(db_session, "zip3") == len(fresh)
    assert await _count(db_session, "state") == 1
    assert await uow.hpi.latest_quarter("zip3") is not None


async def test_replace_series_refuses_an_empty_list_and_keeps_the_old_rows(uow, db_session) -> None:
    await uow.hpi.replace_series("zip3", [_data("010", 2020, 1)])

    with pytest.raises(ValueError, match="empty"):
        await uow.hpi.replace_series("zip3", [])

    assert await _count(db_session, "zip3") == 1


async def test_get_series_and_latest_quarter(uow) -> None:
    await uow.hpi.replace_series(
        "zip3",
        [_data("010", 2020, 4), _data("010", 2021, 2, "105.50"), _data("011", 2022, 1)],
    )

    series = await uow.hpi.get_series("zip3", "010")

    assert [(r.year, r.quarter, r.index_value) for r in series] == [
        (2020, 4, Decimal("100.00")),
        (2021, 2, Decimal("105.50")),
    ]
    assert await uow.hpi.latest_quarter("zip3", "010") == (2021, 2)
    assert await uow.hpi.latest_quarter("zip3") == (2022, 1)
    assert await uow.hpi.latest_quarter("state", "NC") is None


async def test_upsert_status_creates_then_updates_the_single_row(uow, db_session) -> None:
    assert await uow.hpi.get_status() is None
    attempt = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)

    created = await uow.hpi.upsert_status(last_attempt_at=attempt)
    updated = await uow.hpi.upsert_status(last_success_at=attempt, latest_year=2026, latest_quarter=2, last_error=None)
    untouched = await uow.hpi.upsert_status()

    assert created.id == updated.id == untouched.id == 1
    count = (await db_session.execute(select(func.count()).select_from(HpiRefreshStatus))).scalar_one()
    assert count == 1
    status = await uow.hpi.get_status()
    assert status is not None
    assert (status.last_attempt_at, status.last_success_at) == (attempt, attempt)
    assert (status.latest_year, status.latest_quarter, status.last_error) == (2026, 2, None)


async def test_upsert_status_rejects_unknown_fields(uow) -> None:
    with pytest.raises(ValueError, match="bogus"):
        await uow.hpi.upsert_status(bogus=1)
