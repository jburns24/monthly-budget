"""Unit tests for hpi_service (refresh job, staleness) against the in-memory adapter. No network, no database."""

import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest

from app.models.house_price_index import HousePriceIndex
from app.services import hpi_service
from tests.unit.conftest import seed

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def make_xlsx(rows: list[tuple[int, int, int, float | None]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for filler in ("House Price Indexes for Three-Digit ZIP Codes", "", "", ""):
        sheet.append([filler])
    sheet.append(["Three-Digit ZIP Code", "Year", "Quarter", "Index (NSA)", "Index Type"])
    for row in rows:
        sheet.append([*row, "Developmental Index"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class FakeFetcher:
    def __init__(self, xlsx: bytes | None = None, csv: str | None = None, error: Exception | None = None) -> None:
        self.xlsx = xlsx if xlsx is not None else make_xlsx([(276, 2026, 1, 110.0), (276, 2026, 2, 112.5)])
        self.csv = csv if csv is not None else "NC,2026,1,200.00\nNC,2026,2,205.00\nNC,2025,4,\n"
        self.error = error
        self.calls = 0

    async def fetch_zip3_xlsx(self) -> bytes:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.xlsx

    async def fetch_state_csv(self) -> str:
        if self.error is not None:
            raise self.error
        return self.csv


class _Lock:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired

    @asynccontextmanager
    async def __call__(self):
        yield self.acquired


def refresher(uow, fetcher, *, acquired: bool = True) -> hpi_service.HpiRefresher:
    @asynccontextmanager
    async def uow_factory():
        yield uow
        await uow.commit()  # like the real factory: each use is its own committed transaction

    return hpi_service.HpiRefresher(fetcher, uow_factory, _Lock(acquired), clock=lambda: NOW)


async def test_refresh_replaces_both_series_and_records_success(uow) -> None:
    await seed(uow, HousePriceIndex(series="zip3", geo_code="999", year=2000, quarter=1, index_value=Decimal(1)))

    ran = await refresher(uow, FakeFetcher()).run()

    assert ran is True
    assert [(r.year, r.quarter, r.index_value) for r in await uow.hpi.get_series("zip3", "276")] == [
        (2026, 1, Decimal("110.00")),
        (2026, 2, Decimal("112.50")),
    ]
    assert await uow.hpi.get_series("zip3", "999") == []  # series replaced wholesale
    assert [r.index_value for r in await uow.hpi.get_series("state", "NC")] == [Decimal("200.00"), Decimal("205.00")]
    status = await uow.hpi.get_status()
    assert status is not None
    assert (status.last_attempt_at, status.last_success_at) == (NOW, NOW)
    assert (status.latest_year, status.latest_quarter, status.last_error) == (2026, 2, None)


async def test_a_download_failure_records_last_error_and_keeps_old_data(uow) -> None:
    await seed(uow, HousePriceIndex(series="zip3", geo_code="276", year=2025, quarter=1, index_value=Decimal(90)))

    ran = await refresher(uow, FakeFetcher(error=RuntimeError("fhfa is down"))).run()

    assert ran is True
    assert len(await uow.hpi.get_series("zip3", "276")) == 1
    status = await uow.hpi.get_status()
    assert status is not None
    assert status.last_attempt_at == NOW and status.last_success_at is None
    assert status.last_error is not None and "fhfa is down" in status.last_error


async def test_a_garbled_download_records_last_error_and_imports_nothing(uow) -> None:
    ran = await refresher(uow, FakeFetcher(xlsx=b"not an xlsx")).run()

    assert ran is True
    assert await uow.hpi.latest_quarter("zip3") is None
    status = await uow.hpi.get_status()
    assert status is not None and status.last_error


async def test_a_failure_after_a_success_keeps_the_success_timestamp(uow) -> None:
    await refresher(uow, FakeFetcher()).run()

    await refresher(uow, FakeFetcher(error=RuntimeError("boom"))).run(force=True)

    status = await uow.hpi.get_status()
    assert status is not None
    assert status.last_success_at == NOW and status.last_error == "boom"
    assert (status.latest_year, status.latest_quarter) == (2026, 2)


async def test_run_skips_when_another_worker_holds_the_lock(uow) -> None:
    fetcher = FakeFetcher()

    ran = await refresher(uow, fetcher, acquired=False).run()

    assert ran is False and fetcher.calls == 0
    assert await uow.hpi.get_status() is None


async def test_run_skips_when_data_is_fresh_unless_forced(uow) -> None:
    await uow.hpi.upsert_status(last_attempt_at=NOW - timedelta(days=1))
    fetcher = FakeFetcher()

    assert await refresher(uow, fetcher).run() is False
    assert fetcher.calls == 0
    assert await refresher(uow, fetcher).run(force=True) is True
    assert fetcher.calls == 1


@pytest.mark.parametrize(
    ("last_attempt", "expected"),
    [
        (None, True),
        (NOW - timedelta(days=6, hours=23), False),
        (NOW - timedelta(days=7, seconds=1), True),
    ],
)
async def test_is_stale(uow, last_attempt, expected) -> None:
    if last_attempt is not None:
        await uow.hpi.upsert_status(last_attempt_at=last_attempt)

    assert await hpi_service.is_stale(uow, NOW) is expected


async def test_is_stale_with_no_status_row(uow) -> None:
    assert await hpi_service.is_stale(uow, NOW) is True


async def test_parsing_runs_off_the_event_loop_thread(uow) -> None:
    threads: list[threading.Thread] = []
    real_parse = hpi_service.parse_zip3_xlsx

    def recording_parse(data: bytes):
        threads.append(threading.current_thread())
        return real_parse(data)

    with patch.object(hpi_service, "parse_zip3_xlsx", recording_parse):
        await refresher(uow, FakeFetcher()).run()

    assert threads and threads[0] is not threading.main_thread()


async def test_a_database_error_while_storing_is_recorded_as_last_error(uow) -> None:
    async def broken_replace(series, rows):
        raise RuntimeError("connection reset while inserting")

    uow.hpi.replace_series = broken_replace  # type: ignore[method-assign]

    ran = await refresher(uow, FakeFetcher()).run()

    assert ran is True
    status = await uow.hpi.get_status()
    assert status is not None
    assert status.last_error is not None and "connection reset" in status.last_error
    assert status.last_success_at is None and status.last_attempt_at == NOW


async def test_a_download_with_no_rows_fails_without_wiping_existing_data(uow) -> None:
    await seed(uow, HousePriceIndex(series="zip3", geo_code="276", year=2025, quarter=1, index_value=Decimal(90)))

    await refresher(uow, FakeFetcher(xlsx=make_xlsx([]))).run()

    assert len(await uow.hpi.get_series("zip3", "276")) == 1
    status = await uow.hpi.get_status()
    assert status is not None and status.last_error is not None and "no data rows" in status.last_error


@pytest.mark.parametrize(
    ("last_attempt", "expected_wait"),
    [
        (None, None),
        (NOW - timedelta(minutes=10), timedelta(minutes=50)),
        (NOW - timedelta(hours=1), None),
        (NOW - timedelta(days=2), None),
    ],
)
async def test_force_cooldown_remaining(uow, last_attempt, expected_wait) -> None:
    if last_attempt is not None:
        await uow.hpi.upsert_status(last_attempt_at=last_attempt)

    assert await hpi_service.force_cooldown_remaining(uow, NOW) == expected_wait


class _ExplodingRefresher:
    async def run(self, *, force: bool = False) -> bool:
        raise RuntimeError("lock connection refused")


async def test_a_background_refresh_is_referenced_until_done_and_its_failure_is_logged(uow) -> None:
    from unittest.mock import patch as _patch

    with (
        _patch.object(hpi_service.settings, "hpi_auto_refresh", True),
        _patch.object(hpi_service.logger, "error") as log_error,
    ):
        await hpi_service.ensure_fresh(uow, _ExplodingRefresher())  # type: ignore[arg-type]
        assert len(hpi_service._background_refreshes) == 1  # strongly referenced while in flight

        await hpi_service.drain_background_refreshes()
        await asyncio.sleep(0)

    assert hpi_service._background_refreshes == set()  # released once done
    log_error.assert_called_once()
    assert log_error.call_args.args[0] == "hpi_refresh_task_crashed"
    assert "lock connection refused" in log_error.call_args.kwargs["error"]
