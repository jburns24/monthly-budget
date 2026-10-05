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


async def _make_rule(client, family, category, **overrides) -> dict:
    body = {
        "amount_cents": 1000,
        "category_id": str(category.id),
        "frequency": "monthly",
        "start_date": (date.today() + timedelta(days=10)).isoformat(),
    }
    body.update(overrides)
    resp = await client.post(f"/api/families/{family.id}/recurring-expenses", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_update_changes_future_fields_only(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    rent = await create_test_category(db_session, family, name="Rent")
    fun = await create_test_category(db_session, family, name="Fun")
    start = date.today() - timedelta(days=40)

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, rent, start_date=start.isoformat(), description="old")
        generated = await _count(db_session, uuid.UUID(rule["id"]))
        resp = await client.put(
            f"/api/families/{family.id}/recurring-expenses/{rule['id']}",
            json={"amount_cents": 2500, "description": "", "category_id": str(fun.id)},
        )

    body = resp.json()
    assert resp.status_code == 200
    assert (body["amount_cents"], body["description"], body["category_id"]) == (2500, "", str(fun.id))
    assert generated >= 1
    assert await _count(db_session, uuid.UUID(rule["id"])) == generated
    rows = await db_session.execute(select(Expense).where(Expense.recurring_expense_id == uuid.UUID(rule["id"])))
    assert all(e.amount_cents == 1000 and e.category_id == rent.id for e in rows.scalars())


@pytest.mark.asyncio
async def test_update_rejects_bad_category_and_income_category(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")
    other_user = await create_test_user(db_session, display_name="Other")
    other_family, _ = await create_test_family(db_session, other_user)
    foreign = await create_test_category(db_session, other_family, name="Foreign")

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, cat)
        income = await _make_rule(client, family, cat, entry_type="income", category_id=None)
        base = f"/api/families/{family.id}/recurring-expenses"
        bad = await client.put(f"{base}/{rule['id']}", json={"category_id": str(foreign.id)})
        inc = await client.put(f"{base}/{income['id']}", json={"category_id": str(cat.id)})
        zero = await client.put(f"{base}/{rule['id']}", json={"amount_cents": 0})

    assert bad.status_code == 400
    assert inc.status_code == 400
    assert zero.status_code == 422


@pytest.mark.asyncio
async def test_update_next_due_date_reanchors_schedule(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")
    target = date.today() + timedelta(days=20)

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, cat)
        resp = await client.put(
            f"/api/families/{family.id}/recurring-expenses/{rule['id']}",
            json={"next_due_date": target.isoformat()},
        )

    body = resp.json()
    assert resp.status_code == 200
    assert body["next_due_date"] == body["start_date"] == target.isoformat()


@pytest.mark.asyncio
async def test_update_next_due_date_must_be_after_today_and_before_end(
    db_session, app_with_db, authenticated_client
) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")
    today = recurring_service.family_today(family.timezone)

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, cat, end_date=(today + timedelta(days=60)).isoformat())
        url = f"/api/families/{family.id}/recurring-expenses/{rule['id']}"
        past = await client.put(url, json={"next_due_date": (today - timedelta(days=1)).isoformat()})
        same_day = await client.put(url, json={"next_due_date": today.isoformat()})
        after_end = await client.put(url, json={"next_due_date": (today + timedelta(days=90)).isoformat()})
        unchanged = (await client.get(f"/api/families/{family.id}/recurring-expenses")).json()["recurring_expenses"][0]

    assert past.status_code == same_day.status_code == after_end.status_code == 400
    assert unchanged["next_due_date"] == rule["next_due_date"]


@pytest.mark.asyncio
async def test_update_frequency_restarts_from_next_due(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, cat)
        resp = await client.put(
            f"/api/families/{family.id}/recurring-expenses/{rule['id']}", json={"frequency": "weekly"}
        )

    body = resp.json()
    assert body["frequency"] == "weekly"
    assert body["start_date"] == body["next_due_date"] == rule["next_due_date"]


@pytest.mark.asyncio
async def test_extending_end_date_revives_an_ended_rule(db_session, app_with_db, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")
    today = date.today()

    async with authenticated_client(user) as client:
        # Weekly rule that ended last week: every occurrence already generated.
        rule = await _make_rule(
            client,
            family,
            cat,
            frequency="weekly",
            start_date=(today - timedelta(days=14)).isoformat(),
            end_date=(today - timedelta(days=7)).isoformat(),
        )
        url = f"/api/families/{family.id}/recurring-expenses/{rule['id']}"
        generated = await _count(db_session, uuid.UUID(rule["id"]))
        extended = await client.put(url, json={"end_date": (today + timedelta(days=30)).isoformat()})
        paused = await client.put(url, json={"is_active": False})
        ended_again = await client.put(url, json={"end_date": (today + timedelta(days=45)).isoformat()})

    assert rule["is_active"] is False
    assert extended.json()["is_active"] is True
    assert await _count(db_session, uuid.UUID(rule["id"])) >= generated
    # Extending the end date of a *paused* rule must not silently resume it.
    assert paused.json()["is_active"] is False
    assert ended_again.json()["is_active"] is False


@pytest.mark.asyncio
async def test_end_date_before_next_due_stops_rule_and_resume_needs_extension(
    db_session, app_with_db, authenticated_client
) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Rent")

    async with authenticated_client(user) as client:
        rule = await _make_rule(client, family, cat)
        url = f"/api/families/{family.id}/recurring-expenses/{rule['id']}"
        stopped = await client.put(url, json={"end_date": date.today().isoformat()})
        resume = await client.put(url, json={"is_active": True})

    assert stopped.json()["is_active"] is False
    assert resume.status_code == 400


@pytest.mark.asyncio
async def test_update_other_family_rule_is_404(db_session, app_with_db, authenticated_client) -> None:
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    cat = await create_test_category(db_session, family, name="Rent")
    outsider = await create_test_user(db_session, display_name="Outsider")
    other_family, _ = await create_test_family(db_session, outsider)

    async with authenticated_client(owner) as client:
        rule = await _make_rule(client, family, cat)
    async with authenticated_client(outsider) as client:
        resp = await client.put(
            f"/api/families/{other_family.id}/recurring-expenses/{rule['id']}", json={"amount_cents": 5}
        )

    assert resp.status_code == 404
