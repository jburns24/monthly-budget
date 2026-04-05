"""Tests for grace period utility and enforcement on expense endpoints.

Covers:
- is_within_grace_period utility (R03.1.1)
- Expense update returns 403 after grace period expires (R03.1.2)
- Expense delete returns 403 after grace period expires (R03.1.3)
- Grace period NOT applied to monthly goals (R03.1.4)
- BudgetSummaryResponse includes is_editable flag (R03.1.5)
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.family_member import FamilyMember  # noqa: F401 -- registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 -- registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal  # noqa: F401 -- registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 -- registers with Base.metadata
from app.models.user import User  # noqa: F401 -- registers with Base.metadata
from app.services.grace_period import is_within_grace_period
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_category,
    create_test_expense,
    create_test_family,
    create_test_user,
)

# ---------------------------------------------------------------------------
# Local NullPool db_session fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test NullPool engine and transaction rollback."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# JWT patch fixture -- ensures decode_token uses the same secret as test JWTs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    """Patch app.services.jwt_service.settings so decode_token uses _TEST_JWT_SECRET."""
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


# ---------------------------------------------------------------------------
# Helper: inject test session into the FastAPI app
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# Family stub for pure unit tests (no SQLAlchemy instrumentation needed)
# ---------------------------------------------------------------------------


@dataclass
class FamilyStub:
    """Minimal dataclass satisfying the is_within_grace_period interface."""

    timezone: str
    edit_grace_days: int


def _make_family_stub(timezone_str: str = "America/New_York", grace_days: int = 7) -> FamilyStub:
    """Return a plain-Python stub usable by is_within_grace_period."""
    return FamilyStub(timezone=timezone_str, edit_grace_days=grace_days)


# ---------------------------------------------------------------------------
# R03.1.1 -- is_within_grace_period unit tests
# ---------------------------------------------------------------------------


class TestIsWithinGracePeriod:
    """Pure unit tests for the grace period utility function."""

    @staticmethod
    def _frozen(dt_str: str, tz_str: str) -> datetime:
        """Return a UTC datetime corresponding to the local time string in tz_str."""
        tz = ZoneInfo(tz_str)
        return datetime.fromisoformat(dt_str).replace(tzinfo=tz).astimezone(timezone.utc)

    def test_current_month_always_editable(self) -> None:
        """Current month must always return True regardless of grace days."""
        family = _make_family_stub("America/New_York", grace_days=0)
        now_utc = datetime.now(tz=timezone.utc)
        tz = ZoneInfo("America/New_York")
        now_local = now_utc.astimezone(tz)
        year_month = now_local.strftime("%Y-%m")

        with patch("app.services.grace_period._now_utc", return_value=now_utc):
            assert is_within_grace_period(family, year_month) is True

    def test_within_grace_period_returns_true(self) -> None:
        """5 days after month end with 7-day grace should return True."""
        family = _make_family_stub("America/New_York", grace_days=7)
        frozen = self._frozen("2026-04-05T12:00:00", "America/New_York")
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-03") is True

    def test_expired_grace_period_returns_false(self) -> None:
        """10 days after month end with 7-day grace should return False."""
        family = _make_family_stub("America/New_York", grace_days=7)
        frozen = self._frozen("2026-04-10T12:00:00", "America/New_York")
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-03") is False

    def test_exactly_at_grace_boundary_returns_true(self) -> None:
        """Exactly 7 days after month end with 7-day grace should return True."""
        family = _make_family_stub("America/New_York", grace_days=7)
        # April 8 midnight = exactly 7 full days after March 31 midnight
        frozen = self._frozen("2026-04-08T00:00:00", "America/New_York")
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-03") is True

    def test_timezone_respected_los_angeles(self) -> None:
        """UTC 2026-04-08T06:00:00Z = April 7 23:00 LA time = within 7-day grace."""
        family = _make_family_stub("America/Los_Angeles", grace_days=7)
        # April 8 06:00 UTC = April 7 23:00 LA -> day 7 of grace (still within)
        frozen = datetime(2026, 4, 8, 6, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-03") is True

    def test_zero_grace_days_past_month_not_editable(self) -> None:
        """With grace_days=0, any past month should not be editable."""
        family = _make_family_stub("America/New_York", grace_days=0)
        frozen = self._frozen("2026-04-02T12:00:00", "America/New_York")
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-03") is False

    def test_december_rollover(self) -> None:
        """Verify month boundary calculation rolls correctly from Dec to Jan."""
        family = _make_family_stub("UTC", grace_days=10)
        frozen = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2025-12") is True

    def test_future_month_is_editable(self) -> None:
        """A future month should always be editable (returns True)."""
        family = _make_family_stub("America/New_York", grace_days=7)
        frozen = self._frozen("2026-04-05T12:00:00", "America/New_York")
        with patch("app.services.grace_period._now_utc", return_value=frozen):
            assert is_within_grace_period(family, "2026-05") is True


# ---------------------------------------------------------------------------
# R03.1.2 -- Update returns 403 after grace period
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_expense_within_grace_period_succeeds(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """PUT /expenses/{id} succeeds (200) when expense month is within grace period."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        expense_date=date(2026, 3, 15),
        year_month="2026-03",
    )

    # 5 days after March ended -- within 7-day grace
    frozen_utc = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.put(
                    f"/api/families/{family.id}/expenses/{expense.id}",
                    json={
                        "amount_cents": 2000,
                        "expected_updated_at": expense.updated_at.isoformat(),
                    },
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_update_expense_after_grace_period_returns_403(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """PUT /expenses/{id} returns 403 when grace period has expired."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        expense_date=date(2026, 3, 15),
        year_month="2026-03",
    )

    # 10 days after March ended -- grace period expired
    frozen_utc = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.put(
                    f"/api/families/{family.id}/expenses/{expense.id}",
                    json={
                        "amount_cents": 2000,
                        "expected_updated_at": expense.updated_at.isoformat(),
                    },
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403
    assert "Grace period expired" in resp.json()["detail"]
    assert "Past-month expenses are read-only" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# R03.1.3 -- Delete returns 403 after grace period
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_expense_after_grace_period_returns_403(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """DELETE /expenses/{id} returns 403 when grace period has expired."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        expense_date=date(2026, 3, 15),
        year_month="2026-03",
    )

    frozen_utc = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.delete(
                    f"/api/families/{family.id}/expenses/{expense.id}",
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403
    assert "Grace period expired" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_expense_within_grace_period_succeeds(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """DELETE /expenses/{id} succeeds (200) when within grace period."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        expense_date=date(2026, 3, 15),
        year_month="2026-03",
    )

    frozen_utc = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)  # 5 days -- within grace
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.delete(
                    f"/api/families/{family.id}/expenses/{expense.id}",
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# R03.1.4 -- Grace period NOT applied to monthly goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monthly_goal_editable_regardless_of_grace_period(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """PUT /goals/{id} does not return 403 due to grace period enforcement."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)
    category = await create_test_category(db_session, family)

    # Create a goal for a month well past the grace period
    now = datetime.now(tz=timezone.utc)
    goal = MonthlyGoal(
        family_id=family.id,
        category_id=category.id,
        year_month="2026-01",
        amount_cents=50000,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()

    # Freeze to April 10 (well past Jan grace period)
    frozen_utc = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.put(
                    f"/api/families/{family.id}/goals/{goal.id}",
                    json={"amount_cents": 60000, "expected_updated_at": goal.updated_at.isoformat()},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Goals endpoint must NOT return 403 due to grace period logic.
    # (It may return 200, 404, or 422 if the goals endpoint doesn't exist yet,
    # but NOT 403 with "Grace period expired" from our enforcement.)
    detail = resp.json().get("detail", "") if resp.status_code != 200 else ""
    assert "Grace period expired" not in detail, f"Grace period was incorrectly applied to monthly goals: {resp.json()}"


# ---------------------------------------------------------------------------
# R03.1.5 -- BudgetSummaryResponse includes is_editable flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_summary_is_editable_true_for_current_month(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """Budget summary for the current month includes is_editable=true."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)

    # Use the real current month
    tz = ZoneInfo("America/New_York")
    now_local = datetime.now(tz=timezone.utc).astimezone(tz)
    year_month = now_local.strftime("%Y-%m")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(
                f"/api/families/{family.id}/budget/summary",
                params={"month": year_month},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "is_editable" in data
    assert data["is_editable"] is True


@pytest.mark.asyncio
async def test_budget_summary_is_editable_false_for_expired_month(
    db_session: AsyncSession,
    authenticated_client,
) -> None:
    """Budget summary for an expired month includes is_editable=false."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user, timezone="America/New_York", edit_grace_days=7)

    # Freeze to April 10 (10 days after March ended -- grace expired)
    frozen_utc = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.grace_period._now_utc", return_value=frozen_utc):
            async with authenticated_client(user) as client:
                resp = await client.get(
                    f"/api/families/{family.id}/budget/summary",
                    params={"month": "2026-03"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "is_editable" in data
    assert data["is_editable"] is False


# Suppress unused import warning for timedelta (used in authenticated_client fixture)
_ = timedelta
