"""Repository protocol for the cached FHFA house price index and its refresh status."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus


class HpiRepository(Protocol):
    """Reads and writes for :class:`~app.models.house_price_index.HousePriceIndex` and the refresh status row."""

    async def replace_series(self, series: str, rows: Sequence[Mapping[str, Any]]) -> None:
        """Delete every row of ``series`` and bulk insert ``rows`` in its place.

        Each row is a plain mapping with ``geo_code``, ``year``, ``quarter`` and ``index_value``
        (no ORM objects: a ZIP3 import is ~110k rows). Applied within the caller's transaction, so
        readers never see a half-replaced series. Raises ``ValueError`` for an empty ``rows``
        *before* deleting anything, so a bad download can never wipe good data.
        """
        ...

    async def get_series(self, series: str, geo_code: str) -> list[HousePriceIndex]:
        """Return one region's observations, oldest quarter first."""
        ...

    async def latest_quarter(self, series: str, geo_code: str | None = None) -> tuple[int, int] | None:
        """Return the newest ``(year, quarter)`` held for a region, or for the whole series if ``geo_code`` is None.

        None when there is no data.
        """
        ...

    async def get_status(self) -> HpiRefreshStatus | None:
        """Return the single refresh-status row, or None if no refresh was ever attempted."""
        ...

    async def upsert_status(self, **fields: Any) -> HpiRefreshStatus:
        """Create the status row if missing, set ``fields`` on it, and return it.

        ``fields`` are column names of :class:`~app.models.house_price_index.HpiRefreshStatus`
        other than ``id``; an unknown name raises ``ValueError``. Safe against two
        callers creating the row at once.
        """
        ...
