"""Unit tests for the in-memory HpiRepository and the store's composite-key support. No database."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus
from tests.unit.conftest import seed


def _row(series: str, geo: str, year: int, quarter: int, value: str = "100.00") -> HousePriceIndex:
    return HousePriceIndex(series=series, geo_code=geo, year=year, quarter=quarter, index_value=Decimal(value))


def _data(geo: str, year: int, quarter: int, value: str = "100.00") -> dict:
    return {"geo_code": geo, "year": year, "quarter": quarter, "index_value": Decimal(value)}


async def test_replace_series_inserts_rows_keyed_by_the_composite_primary_key(uow) -> None:
    await uow.hpi.replace_series("zip3", [_data("010", 2020, 1), _data("010", 2020, 2)])
    await uow.flush()

    series = await uow.hpi.get_series("zip3", "010")

    assert [(r.year, r.quarter) for r in series] == [(2020, 1), (2020, 2)]


async def test_replace_series_swaps_one_series_and_leaves_the_other(uow) -> None:
    await seed(uow, _row("zip3", "010", 2020, 1, "100.00"), _row("state", "NC", 2020, 1, "200.00"))

    # Same primary key as an existing row, plus a new quarter: the old row must not collide.
    await uow.hpi.replace_series("zip3", [_data("010", 2020, 1, "111.00"), _data("010", 2020, 2)])
    await uow.flush()

    zip3 = await uow.hpi.get_series("zip3", "010")
    assert [(r.quarter, r.index_value) for r in zip3] == [(1, Decimal("111.00")), (2, Decimal("100.00"))]
    state = await uow.hpi.get_series("state", "NC")
    assert [r.index_value for r in state] == [Decimal("200.00")]


async def test_replace_series_removes_rows_missing_from_the_new_data(uow) -> None:
    await seed(uow, _row("zip3", "010", 2020, 1), _row("zip3", "999", 2020, 1))

    await uow.hpi.replace_series("zip3", [_data("010", 2020, 1)])
    await uow.flush()

    assert await uow.hpi.get_series("zip3", "999") == []


async def test_replace_series_refuses_an_empty_list_and_keeps_the_old_rows(uow) -> None:
    await seed(uow, _row("zip3", "010", 2020, 1))

    with pytest.raises(ValueError, match="empty"):
        await uow.hpi.replace_series("zip3", [])
    await uow.flush()

    assert len(await uow.hpi.get_series("zip3", "010")) == 1


async def test_get_series_is_scoped_to_series_and_geo_and_sorted(uow) -> None:
    await seed(
        uow,
        _row("zip3", "010", 2021, 1),
        _row("zip3", "010", 2020, 4),
        _row("zip3", "011", 2022, 1),
        _row("state", "010", 2022, 1),
    )

    series = await uow.hpi.get_series("zip3", "010")

    assert [(r.year, r.quarter) for r in series] == [(2020, 4), (2021, 1)]


async def test_latest_quarter_per_geo_and_per_series(uow) -> None:
    await seed(
        uow,
        _row("zip3", "010", 2020, 4),
        _row("zip3", "010", 2021, 2),
        _row("zip3", "011", 2022, 1),
        _row("state", "NC", 2021, 3),
    )

    assert await uow.hpi.latest_quarter("zip3", "010") == (2021, 2)
    assert await uow.hpi.latest_quarter("zip3") == (2022, 1)
    assert await uow.hpi.latest_quarter("state", "NC") == (2021, 3)
    assert await uow.hpi.latest_quarter("state", "VT") is None


async def test_status_is_absent_until_first_upsert(uow) -> None:
    assert await uow.hpi.get_status() is None


async def test_upsert_status_creates_then_updates_one_row(uow) -> None:
    attempt = datetime(2026, 10, 1, tzinfo=timezone.utc)

    first = await uow.hpi.upsert_status(last_attempt_at=attempt)
    second = await uow.hpi.upsert_status(last_success_at=attempt, latest_year=2026, latest_quarter=2, last_error=None)

    assert first is second
    assert len(uow.store.rows(HpiRefreshStatus)) == 1
    status = await uow.hpi.get_status()
    assert status is not None
    assert (status.id, status.last_attempt_at, status.latest_year, status.latest_quarter) == (1, attempt, 2026, 2)


async def test_upsert_status_rejects_unknown_fields(uow) -> None:
    with pytest.raises(ValueError, match="bogus"):
        await uow.hpi.upsert_status(bogus=1)
