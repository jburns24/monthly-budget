"""API + Postgres tests for the recurring-expenses endpoints and reconciliation on budget summary."""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.expense import Expense
from app.models.recurring_expense import RecurringExpense
from app.services import recurring_service
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_category,
    create_test_family,
    create_test_user,
)


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
def patch_jwt_secret():
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


def override_get_db(session: AsyncSession):
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


@pytest.fixture
def app_with_db(db_session: AsyncSession):
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db(db_session)
    yield app
    app.dependency_overrides.pop(get_db, None)


async def _count(db: AsyncSession, rule_id: uuid.UUID) -> int:
    result = await db.execute(select(func.count()).select_from(Expense).where(Expense.recurring_expense_id == rule_id))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_create_rule_backfills_and_returns_201(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Rent")
    start = date.today() - timedelta(days=15)

    async with authenticated_client(user) as client:
        resp = await client.post(
            f"/api/families/{family.id}/recurring-expenses",
            json={
                "amount_cents": 120000,
                "description": "Rent",
                "category_id": str(category.id),
                "frequency": "weekly",
                "start_date": start.isoformat(),
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["frequency"] == "weekly" and body["is_active"] is True
    # start, +7d, +14d are all on or before "today" in any US timezone window; allow for tz skew of one.
    assert await _count(db_session, uuid.UUID(body["id"])) in (2, 3)


@pytest.mark.asyncio
async def test_validation_errors(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    url = f"/api/families/{family.id}/recurring-expenses"

    async with authenticated_client(user) as client:
        no_category = await client.post(
            url, json={"amount_cents": 100, "frequency": "monthly", "start_date": "2026-01-01"}
        )
        bad_frequency = await client.post(
            url,
            json={"amount_cents": 100, "entry_type": "income", "frequency": "daily", "start_date": "2026-01-01"},
        )
        bad_range = await client.post(
            url,
            json={
                "amount_cents": 100,
                "entry_type": "income",
                "frequency": "monthly",
                "start_date": "2026-02-01",
                "end_date": "2026-01-01",
            },
        )

    assert no_category.status_code == 422
    assert bad_frequency.status_code == 422
    assert bad_range.status_code == 422


@pytest.mark.asyncio
async def test_budget_summary_reconciles_due_rules_once(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Rent")
    today = recurring_service.family_today(family.timezone)
    rule = RecurringExpense(
        family_id=family.id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=50000,
        description="Gym",
        entry_type="expense",
        frequency="monthly",
        start_date=recurring_service._add_months(today, -2),
        next_due_date=recurring_service._add_months(today, -2),
    )
    db_session.add(rule)
    await db_session.flush()

    async with authenticated_client(user) as client:
        first = await client.get(f"/api/families/{family.id}/budget/summary", params={"month": today.strftime("%Y-%m")})
        generated_after_first = await _count(db_session, rule.id)
        second = await client.get(
            f"/api/families/{family.id}/budget/summary", params={"month": today.strftime("%Y-%m")}
        )
        generated_after_second = await _count(db_session, rule.id)

    assert first.status_code == 200 and second.status_code == 200
    assert generated_after_first == 3  # two months ago, last month, this month
    assert generated_after_second == generated_after_first  # idempotent
    assert first.json()["total_spent_cents"] == 50000  # this month's occurrence is counted in the summary


@pytest.mark.asyncio
async def test_unique_index_blocks_duplicate_occurrence(db_session) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Rent")
    rule = RecurringExpense(
        family_id=family.id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=100,
        description="x",
        frequency="monthly",
        start_date=date(2026, 1, 1),
        next_due_date=date(2026, 1, 1),
    )
    db_session.add(rule)
    await db_session.flush()

    def row() -> Expense:
        return Expense(
            family_id=family.id,
            user_id=user.id,
            category_id=category.id,
            amount_cents=100,
            description="x",
            expense_date=date(2026, 1, 1),
            year_month="2026-01",
            recurring_expense_id=rule.id,
        )

    db_session.add(row())
    await db_session.flush()
    db_session.add(row())
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_update_and_delete_endpoints(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Rent")
    base = f"/api/families/{family.id}/recurring-expenses"
    future = (date.today() + timedelta(days=40)).isoformat()

    async with authenticated_client(user) as client:
        created = (
            await client.post(
                base,
                json={
                    "amount_cents": 100,
                    "category_id": str(category.id),
                    "frequency": "monthly",
                    "start_date": future,
                },
            )
        ).json()
        updated = await client.put(f"{base}/{created['id']}", json={"amount_cents": 250, "end_date": None})
        empty = await client.put(f"{base}/{created['id']}", json={})
        listed = await client.get(base)
        deleted = await client.delete(f"{base}/{created['id']}")
        missing = await client.delete(f"{base}/{created['id']}")

    assert updated.status_code == 200 and updated.json()["amount_cents"] == 250
    assert empty.status_code == 400
    assert [r["id"] for r in listed.json()["recurring_expenses"]] == [created["id"]]
    assert deleted.status_code == 200
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_other_family_cannot_see_rules(db_session, app_with_db, authenticated_client) -> None:
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    async with authenticated_client(outsider) as client:
        resp = await client.get(f"/api/families/{family.id}/recurring-expenses")

    assert resp.status_code in (403, 404)
