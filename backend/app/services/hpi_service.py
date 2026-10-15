"""House price index refresh: keep the local copy of the FHFA index no older than a week.

There is no scheduler, so asset requests call :func:`ensure_fresh`, which only *schedules*
a background :meth:`HpiRefresher.run` when the data is missing or stale; the request never waits
for a download. ``run`` is single-flight across gunicorn workers through an advisory lock, records
every attempt in the status row (so a failing download is retried weekly, not on every request) and
replaces each series in one transaction, so readers never see a half-imported index.
"""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.logging import get_logger
from app.ports.unit_of_work import UnitOfWork
from app.services.assets.hpi_import import HpiRow, parse_state_csv, parse_zip3_xlsx
from app.services.hpi_fetcher import HpiFetcher

logger = get_logger(__name__)

STALE_AFTER = timedelta(days=7)
FORCE_COOLDOWN = timedelta(hours=1)
_MAX_ERROR_LENGTH = 1000


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def is_stale(uow: UnitOfWork, now: datetime) -> bool:
    """True when no refresh was ever attempted, or the last attempt is more than a week old."""
    status = await uow.hpi.get_status()
    return status is None or status.last_attempt_at is None or now - status.last_attempt_at > STALE_AFTER


@dataclass(frozen=True)
class _ParsedIndex:
    zip3: list[dict[str, Any]]
    state: list[dict[str, Any]]
    latest: tuple[int, int]


def _as_mappings(rows: list[HpiRow]) -> list[dict[str, Any]]:
    return [{"geo_code": r.geo_code, "year": r.year, "quarter": r.quarter, "index_value": r.index_value} for r in rows]


def _parse(zip3_xlsx: bytes, state_csv: str) -> _ParsedIndex:
    """Parse both files into plain row mappings. CPU-bound (~15s for the workbook): run it in a thread."""
    zip3 = parse_zip3_xlsx(zip3_xlsx)
    state = parse_state_csv(state_csv)
    return _ParsedIndex(_as_mappings(zip3), _as_mappings(state), max((r.year, r.quarter) for r in zip3))


async def force_cooldown_remaining(uow: UnitOfWork, now: datetime) -> timedelta | None:
    """How much longer a *forced* refresh must wait, or None when one is allowed.

    Forced refreshes (the admin endpoint) are refused for an hour after any attempt, so they
    cannot be used to hammer fhfa.gov or to keep the database busy.
    """
    status = await uow.hpi.get_status()
    if status is None or status.last_attempt_at is None:
        return None
    remaining = FORCE_COOLDOWN - (now - status.last_attempt_at)
    return remaining if remaining > timedelta(0) else None


class HpiRefresher:
    """Downloads, parses and stores the index.

    ``uow_factory`` yields a unit of work that commits on exit (each use is its own transaction);
    ``lock_factory`` yields True when this process holds the single-flight lock.
    """

    def __init__(
        self,
        fetcher: HpiFetcher,
        uow_factory: Callable[[], AbstractAsyncContextManager[UnitOfWork]],
        lock_factory: Callable[[], AbstractAsyncContextManager[bool]],
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._fetcher = fetcher
        self._uow_factory = uow_factory
        self._lock_factory = lock_factory
        self._clock = clock

    async def run(self, *, force: bool = False) -> bool:
        """Refresh the index. Returns False when skipped (lock held elsewhere, or fresh and not ``force``).

        A failed download is recorded in the status row's ``last_error`` rather than raised.
        """
        async with self._lock_factory() as acquired:
            if not acquired:
                logger.info("hpi_refresh_skipped_lock_held")
                return False
            now = self._clock()
            async with self._uow_factory() as uow:
                # Re-check under the lock: another worker may have just finished.
                if not force and not await is_stale(uow, now):
                    return False
                # Committed before downloading, so concurrent requests stop scheduling refreshes.
                await uow.hpi.upsert_status(last_attempt_at=now)
            try:
                zip3_xlsx = await self._fetcher.fetch_zip3_xlsx()
                state_csv = await self._fetcher.fetch_state_csv()
                parsed = await asyncio.to_thread(_parse, zip3_xlsx, state_csv)
                async with self._uow_factory() as uow:
                    await uow.hpi.replace_series("zip3", parsed.zip3)
                    await uow.hpi.replace_series("state", parsed.state)
                    await uow.hpi.upsert_status(
                        last_success_at=now,
                        latest_year=parsed.latest[0],
                        latest_quarter=parsed.latest[1],
                        last_error=None,
                    )
            except Exception as exc:
                logger.warning("hpi_refresh_failed", error=str(exc), error_type=type(exc).__name__)
                async with self._uow_factory() as uow:
                    await uow.hpi.upsert_status(last_error=(str(exc) or type(exc).__name__)[:_MAX_ERROR_LENGTH])
                return True
            logger.info(
                "hpi_refresh_succeeded", zip3_rows=len(parsed.zip3), state_rows=len(parsed.state), latest=parsed.latest
            )
            return True


# Strong references to in-flight refresh tasks: the event loop only keeps weak ones, so an
# unreferenced task can be garbage-collected mid-download.
_background_refreshes: set["asyncio.Task[bool]"] = set()


def _finish(task: "asyncio.Task[bool]") -> None:
    """Release the task and log anything ``run`` let escape, so it is never "exception was never retrieved"."""
    _background_refreshes.discard(task)
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("hpi_refresh_task_crashed", error=str(exc) or type(exc).__name__, error_type=type(exc).__name__)


async def ensure_fresh(uow: UnitOfWork, refresher: "HpiRefresher") -> None:
    """Start a background refresh if the index is missing or stale. Never waits for it.

    Deliberately a detached ``asyncio`` task rather than FastAPI's ``BackgroundTasks``: FastAPI
    runs those *before* the request's ``yield`` dependencies are torn down, so the request's
    database session would stay open (and its uncommitted writes uncommitted) for the whole
    download. That interlocks with anything else touching the same rows.
    """
    if settings.hpi_auto_refresh and await is_stale(uow, _utcnow()):
        task = asyncio.create_task(refresher.run())
        _background_refreshes.add(task)
        task.add_done_callback(_finish)


async def drain_background_refreshes() -> None:
    """Wait for every refresh started by :func:`ensure_fresh` (used by tests)."""
    while _background_refreshes:
        await asyncio.gather(*list(_background_refreshes), return_exceptions=True)
