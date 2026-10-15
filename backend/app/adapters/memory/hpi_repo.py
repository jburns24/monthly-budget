"""In-memory implementation of :class:`~app.ports.repositories.house_price_index.HpiRepository`."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.adapters.memory.store import MemoryStore
from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus

_STATUS_FIELDS = frozenset(
    {"last_attempt_at", "last_success_at", "latest_year", "latest_quarter", "last_error"},
)


class MemoryHpiRepository:
    """House price index reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def replace_series(self, series: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            raise ValueError("refusing to replace a house price index series with an empty list")
        for existing in self._store.rows(HousePriceIndex):
            if existing.series == series:
                self._store.delete(existing)
        self._store.add_all(
            HousePriceIndex(
                series=series,
                geo_code=r["geo_code"],
                year=r["year"],
                quarter=r["quarter"],
                index_value=r["index_value"],
            )
            for r in rows
        )

    async def get_series(self, series: str, geo_code: str) -> list[HousePriceIndex]:
        matches = [r for r in self._store.rows(HousePriceIndex) if r.series == series and r.geo_code == geo_code]
        return sorted(matches, key=lambda r: (r.year, r.quarter))

    async def latest_quarter(self, series: str, geo_code: str | None = None) -> tuple[int, int] | None:
        quarters = [
            (r.year, r.quarter)
            for r in self._store.rows(HousePriceIndex)
            if r.series == series and (geo_code is None or r.geo_code == geo_code)
        ]
        return max(quarters, default=None)

    async def get_status(self) -> HpiRefreshStatus | None:
        return self._store.get(HpiRefreshStatus, 1)

    async def upsert_status(self, **fields: Any) -> HpiRefreshStatus:
        unknown = set(fields) - _STATUS_FIELDS
        if unknown:
            raise ValueError(f"unknown HpiRefreshStatus field(s): {', '.join(sorted(unknown))}")
        status = self._store.get(HpiRefreshStatus, 1)
        if status is None:
            # Single-writer store: create and flush at once so a second upsert in this
            # unit of work finds the row instead of staging a duplicate.
            status = HpiRefreshStatus(id=1)
            self._store.add(status)
            self._store.flush()
        for name, value in fields.items():
            setattr(status, name, value)
        return status
