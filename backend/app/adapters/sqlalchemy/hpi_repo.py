"""SQLAlchemy implementation of :class:`~app.ports.repositories.house_price_index.HpiRepository`."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus

# 5 columns per row against asyncpg's 32767 bind-parameter limit.
_INSERT_CHUNK = 5000

_STATUS_FIELDS = frozenset(
    {"last_attempt_at", "last_success_at", "latest_year", "latest_quarter", "last_error"},
)


class SqlAlchemyHpiRepository:
    """House price index reads and writes against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_series(self, series: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            raise ValueError("refusing to replace a house price index series with an empty list")
        # Core bulk insert of plain dicts: a ZIP3 refresh is ~110k rows, far too many for ORM objects.
        await self._session.execute(delete(HousePriceIndex).where(HousePriceIndex.series == series))
        values = [
            {
                "series": series,
                "geo_code": r["geo_code"],
                "year": r["year"],
                "quarter": r["quarter"],
                "index_value": r["index_value"],
            }
            for r in rows
        ]
        for start in range(0, len(values), _INSERT_CHUNK):
            await self._session.execute(pg_insert(HousePriceIndex), values[start : start + _INSERT_CHUNK])

    async def get_series(self, series: str, geo_code: str) -> list[HousePriceIndex]:
        result = await self._session.execute(
            select(HousePriceIndex)
            .where(HousePriceIndex.series == series, HousePriceIndex.geo_code == geo_code)
            .order_by(HousePriceIndex.year, HousePriceIndex.quarter)
        )
        return list(result.scalars().all())

    async def latest_quarter(self, series: str, geo_code: str | None = None) -> tuple[int, int] | None:
        filters = [HousePriceIndex.series == series]
        if geo_code is not None:
            filters.append(HousePriceIndex.geo_code == geo_code)
        result = await self._session.execute(
            select(HousePriceIndex.year, HousePriceIndex.quarter)
            .where(*filters)
            .order_by(HousePriceIndex.year.desc(), HousePriceIndex.quarter.desc())
            .limit(1)
        )
        row = result.first()
        return None if row is None else (row.year, row.quarter)

    async def get_status(self) -> HpiRefreshStatus | None:
        result = await self._session.execute(select(HpiRefreshStatus).where(HpiRefreshStatus.id == 1))
        return result.scalar_one_or_none()

    async def upsert_status(self, **fields: Any) -> HpiRefreshStatus:
        unknown = set(fields) - _STATUS_FIELDS
        if unknown:
            raise ValueError(f"unknown HpiRefreshStatus field(s): {', '.join(sorted(unknown))}")
        statement = pg_insert(HpiRefreshStatus).values(id=1, **fields)
        if fields:
            statement = statement.on_conflict_do_update(index_elements=[HpiRefreshStatus.id], set_=fields)
        else:
            statement = statement.on_conflict_do_nothing(index_elements=[HpiRefreshStatus.id])
        await self._session.execute(statement)
        # populate_existing: the identity map may hold a copy from before the upsert.
        result = await self._session.execute(
            select(HpiRefreshStatus).where(HpiRefreshStatus.id == 1).execution_options(populate_existing=True)
        )
        return result.scalar_one()
