"""API + Postgres tests for asset summaries, history, and the house price index refresh."""

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.config import settings
from app.database import get_db
from app.deps.hpi import get_hpi_refresher
from app.models.asset import AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation
from app.models.family_member import FamilyMember
from app.models.house_price_index import HousePriceIndex, HpiRefreshStatus
from app.services import hpi_service
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_asset,
    create_test_category,
    create_test_expense,
    create_test_family,
    create_test_user,
)
from tests.unit.test_hpi_service import FakeFetcher

TODAY = date(2026, 6, 15)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
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


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


@pytest.fixture(autouse=True)
def frozen_today():
    with patch("app.services.asset_analytics.family_today", return_value=TODAY):
        yield


@pytest.fixture
def app_with_db(db_session: AsyncSession):
    from app.main import app

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield app
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_hpi_refresher, None)


def refresher_for(db_session: AsyncSession, fetcher) -> hpi_service.HpiRefresher:
    """A refresher that works inside the test's rolled-back transaction and never takes a real lock."""

    @asynccontextmanager
    async def uow_factory() -> AsyncIterator[SqlAlchemyUnitOfWork]:
        yield SqlAlchemyUnitOfWork(db_session, owns_transaction=False)

    @asynccontextmanager
    async def no_lock() -> AsyncIterator[bool]:
        yield True

    return hpi_service.HpiRefresher(fetcher, uow_factory, no_lock)


class RecordingRefresher:
    def __init__(self) -> None:
        self.runs = 0

    async def run(self, *, force: bool = False) -> bool:
        self.runs += 1
        return True


async def _family(db_session):
    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    return admin, family


async def _member(db_session, family):
    user = await create_test_user(db_session, display_name="Member")
    db_session.add(
        FamilyMember(
            id=uuid.uuid4(),
            family_id=family.id,
            user_id=user.id,
            role="member",
            joined_at=datetime.now(tz=timezone.utc),
        )
    )
    await db_session.flush()
    return user


def _hpi(series, geo, year, quarter, value):
    return HousePriceIndex(series=series, geo_code=geo, year=year, quarter=quarter, index_value=Decimal(value))


async def _house_with_loan(db_session, family, admin, **overrides):
    """A house bought 2024-01-01 for $400k in Raleigh (ZIP3 276), 0% loan of $320k over 320 months ($1000/mo)."""
    for row in (_hpi("zip3", "276", 2024, 1, "100"), _hpi("zip3", "276", 2026, 1, "110")):
        await db_session.merge(row)  # idempotent: tests may build several houses in one region
    asset = await create_test_asset(
        db_session,
        family,
        admin,
        purchase_date=date(2024, 1, 1),
        purchase_price_cents=40_000_000,
        down_payment_cents=8_000_000,
        closing_costs_cents=600_000,
        **overrides,
    )
    db_session.add(
        AssetLoan(
            asset_id=asset.id,
            original_amount_cents=32_000_000,
            annual_interest_rate=Decimal(0),
            term_months=320,
            first_payment_date=date(2024, 2, 1),
            escrow_monthly_cents=40_000,
        )
    )
    await db_session.flush()
    return asset


async def _link(db_session, family, admin, category, asset, role, amount, when):
    return await create_test_expense(
        db_session,
        family,
        admin,
        category,
        asset_id=asset.id,
        asset_role=role,
        amount_cents=amount,
        expense_date=when,
        year_month=when.strftime("%Y-%m"),
    )


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


async def test_detail_summary_for_a_house_with_loan_and_linked_costs(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    asset = await _house_with_loan(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Home")
    await _link(db_session, family, admin, category, asset, "loan_payment", 185_000, date(2026, 5, 1))  # ignored
    await _link(db_session, family, admin, category, asset, "improvement", 1_000_000, date(2026, 2, 1))
    await _link(db_session, family, admin, category, asset, "maintenance", 50_000, date(2026, 5, 1))
    await _link(db_session, family, admin, category, asset, "carrying_cost", 20_000, date(2026, 12, 1))  # future
    db_session.add(
        AssetContribution(
            asset_id=asset.id, contribution_date=date(2025, 1, 1), amount_cents=500_000, role="improvement"
        )
    )
    await db_session.flush()

    async with authenticated_client(admin) as client:
        resp = await client.get(f"/api/families/{family.id}/assets/{asset.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == {
        "market_value_cents": 44_000_000,  # 40M * 110/100: the 2026Q2 lookup clamps to the latest quarter, 2026Q1
        "loan_balance_cents": 29_100_000,  # 29 payments of $1000 since 2024-02
        "equity_cents": 14_900_000,
        "valuation_source": "fhfa_zip3",
        "down_payment_cents": 8_000_000,
        "principal_paid_cents": 2_900_000,
        "improvements_cents": 1_500_000,
        "interest_paid_cents": 0,
        "escrow_paid_cents": 1_160_000,
        "closing_costs_cents": 600_000,
        "maintenance_cents": 50_000,
        "carrying_cost_cents": 0,
        "equity_building_cents": 12_400_000,
        "sunk_cost_cents": 1_810_000,
        "cash_in_cents": 14_210_000,
        "net_gain_cents": None,
    }
    assert body["valuation"] == {"source": "fhfa_zip3", "label": "FHFA ZIP3 276 · 2026Q1"}
    assert body["loan"]["computed_monthly_payment_cents"] == 100_000
    assert body["loan"]["payoff_date_estimate"] == "2050-09-01"  # payment 320 falls 319 months after 2024-02-01


async def test_summary_reflects_balance_corrections_and_manual_valuations(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    asset = await _house_with_loan(db_session, family, admin)
    loan = (await db_session.execute(select(AssetLoan).where(AssetLoan.asset_id == asset.id))).scalar_one()
    db_session.add_all(
        [
            # Paid down $8k more than scheduled by 2025-01-01; the schedule continues from there.
            AssetLoanBalanceCorrection(loan_id=loan.id, as_of_date=date(2025, 1, 1), balance_cents=30_000_000),
            AssetValuation(asset_id=asset.id, as_of_date=date(2026, 3, 1), value_cents=50_000_000),
        ]
    )
    await db_session.flush()

    async with authenticated_client(admin) as client:
        body = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()

    summary = body["summary"]
    assert summary["market_value_cents"] == 50_000_000
    assert summary["loan_balance_cents"] == 28_300_000  # 30M less 17 payments of $1000
    assert summary["principal_paid_cents"] == 3_700_000
    assert summary["equity_cents"] == 21_700_000
    assert len(body["corrections"]) == 1 and len(body["valuations"]) == 1


async def test_sold_asset_is_frozen_at_the_sale_with_a_net_gain(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    asset = await _house_with_loan(
        db_session,
        family,
        admin,
        sold_date=date(2026, 1, 10),
        sale_price_cents=50_000_000,
        selling_costs_cents=300_000,
    )
    category = await create_test_category(db_session, family, name="Home")
    await _link(db_session, family, admin, category, asset, "improvement", 1_000_000, date(2026, 2, 1))  # after sale
    db_session.add(
        AssetContribution(
            asset_id=asset.id, contribution_date=date(2025, 1, 1), amount_cents=500_000, role="improvement"
        )
    )
    await db_session.flush()

    async with authenticated_client(admin) as client:
        body = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()

    summary = body["summary"]
    assert body["is_sold"] is True
    assert summary["market_value_cents"] == 50_000_000
    assert summary["loan_balance_cents"] == 29_600_000  # 24 payments through 2026-01-10
    assert summary["equity_cents"] == 20_400_000
    assert summary["cash_in_cents"] == 12_460_000
    assert summary["net_gain_cents"] == 7_640_000  # 50.0M - 0.3M - 29.6M - 12.46M


async def test_vehicle_depreciates_and_has_no_loan_numbers(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    asset = await create_test_asset(
        db_session,
        family,
        admin,
        asset_type="vehicle",
        state=None,
        zip_code=None,
        purchase_date=date(2025, 6, 15),
        purchase_price_cents=3_000_000,
        down_payment_cents=3_000_000,
        annual_depreciation_rate=Decimal("0.2"),
    )

    async with authenticated_client(admin) as client:
        body = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()

    summary = body["summary"]
    assert 2_300_000 < summary["market_value_cents"] < 2_500_000  # 3.0M * 0.8 ** (365/365.25)
    assert summary["loan_balance_cents"] == 0 and summary["valuation_source"] == "depreciation"
    assert body["loan"] is None and body["valuation"]["source"] == "depreciation"


async def test_list_items_carry_summaries(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    member = await _member(db_session, family)
    asset = await _house_with_loan(db_session, family, admin)

    async with authenticated_client(member) as client:
        resp = await client.get(f"/api/families/{family.id}/assets")

    item = resp.json()["assets"][0]
    assert item["id"] == str(asset.id)
    assert item["has_loan"] is True
    assert item["summary"] == {
        "market_value_cents": 44_000_000,
        "loan_balance_cents": 29_100_000,
        "equity_cents": 14_900_000,
        "cash_in_cents": 12_660_000,  # 8.0M down + 2.9M principal + 1.16M escrow + 0.6M closing
        "valuation_source": "fhfa_zip3",
    }


async def _populated_asset(db_session, family, admin, category, n):
    asset = await _house_with_loan(db_session, family, admin, name=f"House {n}")
    loan = (await db_session.execute(select(AssetLoan).where(AssetLoan.asset_id == asset.id))).scalar_one()
    db_session.add_all(
        [
            AssetLoanBalanceCorrection(loan_id=loan.id, as_of_date=date(2025, 1, 1), balance_cents=30_000_000),
            AssetValuation(asset_id=asset.id, as_of_date=date(2026, 3, 1), value_cents=50_000_000),
            AssetContribution(
                asset_id=asset.id, contribution_date=date(2025, 1, 1), amount_cents=1, role="improvement"
            ),
        ]
    )
    await db_session.flush()
    await _link(db_session, family, admin, category, asset, "maintenance", 1_000, date(2026, 2, 1))


async def _count_queries(db_session, client, url) -> int:
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        resp = await client.get(url)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert resp.status_code == 200
    return len(statements)


async def test_list_query_count_does_not_grow_with_the_number_of_assets(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    category = await create_test_category(db_session, family, name="Home")
    await _populated_asset(db_session, family, admin, category, 1)
    url = f"/api/families/{family.id}/assets"

    async with authenticated_client(admin) as client:
        one = await _count_queries(db_session, client, url)
        for n in range(2, 7):
            await _populated_asset(db_session, family, admin, category, n)
        six = await _count_queries(db_session, client, url)

    # Batch loaded: a fixed number of queries however many assets (the index costs one per distinct region).
    assert one == six
    assert one <= 12


async def test_list_item_without_a_loan_says_so(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    await create_test_asset(db_session, family, admin)

    async with authenticated_client(admin) as client:
        resp = await client.get(f"/api/families/{family.id}/assets")

    assert resp.json()["assets"][0]["has_loan"] is False


async def test_hpi_status_is_reported_on_detail(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    asset = await _house_with_loan(db_session, family, admin)
    db_session.add(HpiRefreshStatus(id=1, latest_year=2026, latest_quarter=1))
    await db_session.flush()

    async with authenticated_client(admin) as client:
        body = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()

    assert body["hpi_status"] == {"latest_year": 2026, "latest_quarter": 1}


async def test_house_with_no_index_data_falls_back_to_the_purchase_price(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    asset = await create_test_asset(db_session, family, admin, purchase_date=date(2024, 1, 1))

    async with authenticated_client(admin) as client:
        body = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()

    assert body["summary"]["market_value_cents"] == 40_000_000
    assert body["summary"]["valuation_source"] == "purchase_price"
    assert body["valuation"] == {"source": "purchase_price", "label": None}
    assert body["hpi_status"] == {"latest_year": None, "latest_quarter": None}


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


async def test_history_returns_monthly_points_ending_at_today(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    member = await _member(db_session, family)
    asset = await _house_with_loan(db_session, family, admin)

    async with authenticated_client(member) as client:
        resp = await client.get(f"/api/families/{family.id}/assets/{asset.id}/history")
        detail = (await client.get(f"/api/families/{family.id}/assets/{asset.id}")).json()
        missing = await client.get(f"/api/families/{family.id}/assets/{uuid.uuid4()}/history")

    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 30  # 2024-01 .. 2026-06
    assert points[0]["date"] == "2024-01-31" and points[-1]["date"] == TODAY.isoformat()
    assert set(points[0]) == {"date", "market_value_cents", "loan_balance_cents", "equity_cents", "cash_in_cents"}
    assert points[0]["loan_balance_cents"] == 32_000_000
    last = points[-1]
    summary = detail["summary"]
    assert (last["market_value_cents"], last["loan_balance_cents"], last["equity_cents"], last["cash_in_cents"]) == (
        summary["market_value_cents"],
        summary["loan_balance_cents"],
        summary["equity_cents"],
        summary["cash_in_cents"],
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# HPI refresh
# ---------------------------------------------------------------------------


async def test_hpi_refresh_endpoint_runs_synchronously_and_returns_status(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher_for(db_session, FakeFetcher())

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets/hpi-refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert (body["latest_year"], body["latest_quarter"], body["last_error"]) == (2026, 2, None)
    assert body["last_attempt_at"] is not None and body["last_success_at"] is not None
    count = (await db_session.execute(select(func.count()).select_from(HousePriceIndex))).scalar_one()
    assert count == 4


async def test_hpi_refresh_endpoint_reports_a_failed_download(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    fetcher = FakeFetcher(error=RuntimeError("fhfa is down"))
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher_for(db_session, fetcher)

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets/hpi-refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert "fhfa is down" in body["last_error"] and body["last_success_at"] is None
    assert body["last_attempt_at"] is not None


async def test_hpi_refresh_endpoint_refuses_a_second_forced_refresh_within_the_hour(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    fetcher = FakeFetcher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher_for(db_session, fetcher)
    url = f"/api/families/{family.id}/assets/hpi-refresh"

    async with authenticated_client(admin) as client:
        first = await client.post(url)
        second = await client.post(url)

    assert first.status_code == 200
    assert second.status_code == 429
    assert 0 < int(second.headers["retry-after"]) <= 3600
    assert fetcher.calls == 1


async def test_hpi_refresh_endpoint_is_allowed_again_after_the_cooldown(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    db_session.add(HpiRefreshStatus(id=1, last_attempt_at=datetime.now(tz=timezone.utc) - timedelta(hours=2)))
    await db_session.flush()
    fetcher = FakeFetcher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher_for(db_session, fetcher)

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets/hpi-refresh")

    assert resp.status_code == 200 and fetcher.calls == 1


async def test_hpi_refresh_endpoint_reports_a_store_failure_instead_of_a_500(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _family(db_session)
    refresher = refresher_for(db_session, FakeFetcher())
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher

    async def broken_replace(self, series, rows):
        raise RuntimeError("disk full")

    async with authenticated_client(admin) as client:
        with patch("app.adapters.sqlalchemy.hpi_repo.SqlAlchemyHpiRepository.replace_series", broken_replace):
            resp = await client.post(f"/api/families/{family.id}/assets/hpi-refresh")

    assert resp.status_code == 200
    assert "disk full" in resp.json()["last_error"] and resp.json()["last_success_at"] is None


async def test_hpi_refresh_endpoint_is_admin_only(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    member = await _member(db_session, family)
    fetcher = FakeFetcher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: refresher_for(db_session, fetcher)

    async with authenticated_client(member) as client:
        resp = await client.post(f"/api/families/{family.id}/assets/hpi-refresh")

    assert resp.status_code == 403 and fetcher.calls == 0


# ---------------------------------------------------------------------------
# lazy refresh scheduling
# ---------------------------------------------------------------------------


@pytest.fixture
def auto_refresh():
    with patch.object(settings, "hpi_auto_refresh", True):
        yield


async def test_asset_requests_schedule_a_refresh_when_the_index_is_missing(
    db_session, app_with_db, authenticated_client, auto_refresh
) -> None:
    admin, family = await _family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    recorder = RecordingRefresher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: recorder
    base = f"/api/families/{family.id}/assets"

    async with authenticated_client(admin) as client:
        await client.get(base)
        await client.get(f"{base}/{asset.id}")
        await client.get(f"{base}/{asset.id}/history")
    await hpi_service.drain_background_refreshes()

    assert recorder.runs == 3


class BlockedRefresher:
    """A refresh that never finishes on its own, like a slow download."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, *, force: bool = False) -> bool:
        self.started.set()
        await self.release.wait()
        return True


async def test_a_slow_refresh_neither_delays_the_response_nor_holds_the_request_transaction(
    db_session, app_with_db, authenticated_client, auto_refresh
) -> None:
    """The refresh must outlive the request without keeping its database transaction open.

    FastAPI runs background tasks *before* tearing down yield-dependencies, so a BackgroundTask
    would keep the request's session (and any uncommitted writes, e.g. a just-created asset) open
    for the whole download.
    """
    admin, family = await _family(db_session)
    blocked = BlockedRefresher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: blocked
    body = {
        "name": "Maple",
        "asset_type": "house",
        "purchase_date": "2024-01-01",
        "purchase_price_cents": 100,
        "state": "NC",
        "zip_code": "27601",
    }

    try:
        async with authenticated_client(admin) as client:
            resp = await asyncio.wait_for(client.post(f"/api/families/{family.id}/assets", json=body), timeout=10)
        await asyncio.wait_for(blocked.started.wait(), timeout=10)
        assert resp.status_code == 201  # returned while the refresh is still running
    finally:
        blocked.release.set()
        await hpi_service.drain_background_refreshes()


async def test_no_refresh_is_scheduled_when_the_index_is_fresh(
    db_session, app_with_db, authenticated_client, auto_refresh
) -> None:
    admin, family = await _family(db_session)
    await create_test_asset(db_session, family, admin)
    db_session.add(HpiRefreshStatus(id=1, last_attempt_at=datetime.now(tz=timezone.utc) - timedelta(days=1)))
    await db_session.flush()
    recorder = RecordingRefresher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: recorder

    async with authenticated_client(admin) as client:
        await client.get(f"/api/families/{family.id}/assets")
    await hpi_service.drain_background_refreshes()

    assert recorder.runs == 0


async def test_no_refresh_is_scheduled_for_families_without_a_house(
    db_session, app_with_db, authenticated_client, auto_refresh
) -> None:
    admin, family = await _family(db_session)
    await create_test_asset(db_session, family, admin, asset_type="vehicle", state=None, zip_code=None)
    recorder = RecordingRefresher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: recorder

    async with authenticated_client(admin) as client:
        await client.get(f"/api/families/{family.id}/assets")
    await hpi_service.drain_background_refreshes()

    assert recorder.runs == 0


async def test_no_refresh_is_scheduled_when_auto_refresh_is_off(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _family(db_session)
    await create_test_asset(db_session, family, admin)
    recorder = RecordingRefresher()
    app_with_db.dependency_overrides[get_hpi_refresher] = lambda: recorder

    async with authenticated_client(admin) as client:
        await client.get(f"/api/families/{family.id}/assets")

    assert settings.hpi_auto_refresh is False  # the suite-wide default
    assert recorder.runs == 0


# ---------------------------------------------------------------------------
# advisory lock (real connections)
# ---------------------------------------------------------------------------


async def test_the_advisory_lock_is_single_flight() -> None:
    from app.deps.hpi import pg_advisory_lock

    async with pg_advisory_lock(918273) as first:
        async with pg_advisory_lock(918273) as second:
            assert (first, second) == (True, False)
    async with pg_advisory_lock(918273) as again:
        assert again is True
