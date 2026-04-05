"""Integration tests for expense lifecycle and RBAC enforcement.

Tests cover:
- Full expense lifecycle: create -> list -> update -> delete
- Budget summary with multiple categories and expenses
- RBAC enforcement: member can CRUD, non-member gets 404

Each test uses the full HTTP API layer with authenticated clients and per-test DB rollback.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.category import Category  # noqa: F401 — registers with Base.metadata
from app.models.expense import Expense  # noqa: F401 — registers with Base.metadata
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember
from app.models.monthly_goal import MonthlyGoal  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import _TEST_JWT_SECRET, create_test_category, create_test_family, create_test_user

# ---------------------------------------------------------------------------
# NullPool db_session fixture — per-test transaction rollback
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback."""
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
# Helpers for HTTP integration tests
# ---------------------------------------------------------------------------


def _override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


def _make_test_jwt(user, expires_in: timedelta = timedelta(minutes=15)) -> str:
    """Create a signed JWT for *user* using the test secret."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user.google_id,
        "user_id": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


def _make_client(app, user, db_session: AsyncSession) -> AsyncClient:
    """Return an AsyncClient wired to *app* with JWT cookies for *user*."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={
            "access_token": _make_test_jwt(user, timedelta(minutes=15)),
            "refresh_token": _make_test_jwt(user, timedelta(days=7)),
        },
    )


# ---------------------------------------------------------------------------
# Test 1: Full expense lifecycle — create -> list -> update -> delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_expense_lifecycle(db_session: AsyncSession) -> None:
    """Full expense lifecycle through the HTTP API.

    Steps:
    1. Create an expense (POST /api/families/{id}/expenses) — expect 201
    2. List expenses for that month — expense appears
    3. Update the expense amount (PUT /api/families/{id}/expenses/{expense_id}) — expect 200
    4. Get single expense — updated values reflected
    5. Delete the expense (DELETE /api/families/{id}/expenses/{expense_id}) — expect 200
    6. List expenses again — list is empty
    """
    from unittest.mock import patch

    from app.main import app

    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET

        admin = await create_test_user(db_session, email="admin@expense-lifecycle.test", display_name="Admin")
        family, _ = await create_test_family(db_session, admin, name="Lifecycle Family")
        category = await create_test_category(db_session, family, name="Groceries")

        app.dependency_overrides[get_db] = _override_get_db(db_session)
        try:
            async with _make_client(app, admin, db_session) as client:
                family_id = str(family.id)

                # Step 1: Create expense
                resp1 = await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 4500,
                        "description": "Weekly shopping",
                        "category_id": str(category.id),
                        "expense_date": "2026-04-05",
                    },
                )
                assert resp1.status_code == 201, f"create failed: {resp1.text}"
                exp_data = resp1.json()
                assert exp_data["amount_cents"] == 4500
                assert exp_data["description"] == "Weekly shopping"
                assert exp_data["expense_date"] == "2026-04-05"
                assert exp_data["family_id"] == family_id
                expense_id = exp_data["id"]
                updated_at = exp_data["updated_at"]

                # Step 2: List expenses — new expense appears
                resp2 = await client.get(f"/api/families/{family_id}/expenses?year_month=2026-04")
                assert resp2.status_code == 200, f"list failed: {resp2.text}"
                expenses = resp2.json()["expenses"]
                assert len(expenses) == 1
                assert expenses[0]["id"] == expense_id
                assert expenses[0]["amount_cents"] == 4500

                # Step 3: Update expense amount and description
                resp3 = await client.put(
                    f"/api/families/{family_id}/expenses/{expense_id}",
                    json={
                        "amount_cents": 6000,
                        "description": "Big weekly shop",
                        "expected_updated_at": updated_at,
                    },
                )
                assert resp3.status_code == 200, f"update failed: {resp3.text}"
                updated = resp3.json()
                assert updated["amount_cents"] == 6000
                assert updated["description"] == "Big weekly shop"
                assert updated["id"] == expense_id

                # Step 4: Get single expense — updated values
                resp4 = await client.get(f"/api/families/{family_id}/expenses/{expense_id}")
                assert resp4.status_code == 200, f"get failed: {resp4.text}"
                fetched = resp4.json()
                assert fetched["amount_cents"] == 6000
                assert fetched["description"] == "Big weekly shop"

                # Step 5: Delete expense
                resp5 = await client.delete(f"/api/families/{family_id}/expenses/{expense_id}")
                assert resp5.status_code == 200, f"delete failed: {resp5.text}"
                del_data = resp5.json()
                assert "message" in del_data

                # Step 6: List expenses — now empty
                resp6 = await client.get(f"/api/families/{family_id}/expenses?year_month=2026-04")
                assert resp6.status_code == 200, f"list after delete failed: {resp6.text}"
                assert resp6.json()["total_count"] == 0
                assert resp6.json()["expenses"] == []
        finally:
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 2: Budget summary with multiple categories and expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_summary_multiple_categories(db_session: AsyncSession) -> None:
    """Budget summary aggregates correctly across multiple categories.

    Steps:
    1. Create 3 categories with monthly goals for two of them
    2. Create several expenses across those categories
    3. Retrieve budget summary for the month
    4. Verify per-category spend and total_spent_cents
    """
    from unittest.mock import patch

    from app.main import app

    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET

        admin = await create_test_user(db_session, email="admin@budget-summary.test", display_name="Admin")
        family, _ = await create_test_family(db_session, admin, name="Budget Family")

        cat_groceries = await create_test_category(db_session, family, name="Groceries", sort_order=0)
        cat_dining = await create_test_category(db_session, family, name="Dining", sort_order=1)
        cat_transport = await create_test_category(db_session, family, name="Transport", sort_order=2)

        # Add monthly goals for groceries and dining
        now = datetime.now(tz=timezone.utc)
        db_session.add(
            MonthlyGoal(
                id=uuid.uuid4(),
                family_id=family.id,
                category_id=cat_groceries.id,
                year_month="2026-04",
                amount_cents=20000,
                created_at=now,
                updated_at=now,
            )
        )
        db_session.add(
            MonthlyGoal(
                id=uuid.uuid4(),
                family_id=family.id,
                category_id=cat_dining.id,
                year_month="2026-04",
                amount_cents=10000,
                created_at=now,
                updated_at=now,
            )
        )
        await db_session.flush()

        app.dependency_overrides[get_db] = _override_get_db(db_session)
        try:
            async with _make_client(app, admin, db_session) as client:
                family_id = str(family.id)

                # Create expenses
                # Groceries: 5000 + 8000 = 13000 (goal 20000 -> 65% -> green)
                await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 5000,
                        "description": "Fruit and veg",
                        "category_id": str(cat_groceries.id),
                        "expense_date": "2026-04-02",
                    },
                )
                await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 8000,
                        "description": "Big grocery run",
                        "category_id": str(cat_groceries.id),
                        "expense_date": "2026-04-10",
                    },
                )
                # Dining: 9000 (goal 10000 -> 90% -> yellow)
                await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 9000,
                        "description": "Restaurant dinner",
                        "category_id": str(cat_dining.id),
                        "expense_date": "2026-04-15",
                    },
                )
                # Transport: 3000 (no goal -> none)
                await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 3000,
                        "description": "Bus pass",
                        "category_id": str(cat_transport.id),
                        "expense_date": "2026-04-01",
                    },
                )

                # Get budget summary
                resp = await client.get(f"/api/families/{family_id}/budget/summary?month=2026-04")
                assert resp.status_code == 200, f"budget summary failed: {resp.text}"
                body = resp.json()

                assert body["year_month"] == "2026-04"
                assert body["total_spent_cents"] == 25000  # 13000 + 9000 + 3000

                cats = {c["category_name"]: c for c in body["categories"]}
                assert set(cats.keys()) == {"Groceries", "Dining", "Transport"}

                # Groceries: 13000 spent / 20000 goal -> 65% green
                g = cats["Groceries"]
                assert g["spent_cents"] == 13000
                assert g["goal_cents"] == 20000
                assert g["status"] == "green"

                # Dining: 9000 spent / 10000 goal -> 90% yellow
                d = cats["Dining"]
                assert d["spent_cents"] == 9000
                assert d["goal_cents"] == 10000
                assert d["status"] == "yellow"

                # Transport: 3000 spent, no goal -> none
                t = cats["Transport"]
                assert t["spent_cents"] == 3000
                assert t["goal_cents"] is None
                assert t["status"] == "none"
        finally:
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 3: RBAC — any family member can CRUD expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_member_can_crud_expenses(db_session: AsyncSession) -> None:
    """Family members (non-admin role) can create, read, update, and delete expenses."""
    from unittest.mock import patch

    from app.main import app

    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET

        admin = await create_test_user(db_session, email="admin@rbac-expenses.test", display_name="Admin")
        member_user = await create_test_user(db_session, email="member@rbac-expenses.test", display_name="Member")
        family, _ = await create_test_family(db_session, admin, name="RBAC Family")

        # Add member_user as a non-admin member
        now = datetime.now(tz=timezone.utc)
        member_record = FamilyMember(
            id=uuid.uuid4(),
            family_id=family.id,
            user_id=member_user.id,
            role="member",
            joined_at=now,
        )
        db_session.add(member_record)
        await db_session.flush()

        category = await create_test_category(db_session, family, name="Bills")

        app.dependency_overrides[get_db] = _override_get_db(db_session)
        try:
            async with _make_client(app, member_user, db_session) as client:
                family_id = str(family.id)

                # Member CAN create an expense
                resp_create = await client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 1500,
                        "description": "Phone bill",
                        "category_id": str(category.id),
                        "expense_date": "2026-04-08",
                    },
                )
                assert resp_create.status_code == 201, f"member create failed: {resp_create.text}"
                exp_id = resp_create.json()["id"]
                exp_updated_at = resp_create.json()["updated_at"]

                # Member CAN list expenses
                resp_list = await client.get(f"/api/families/{family_id}/expenses?year_month=2026-04")
                assert resp_list.status_code == 200, f"member list failed: {resp_list.text}"
                assert any(e["id"] == exp_id for e in resp_list.json()["expenses"])

                # Member CAN update their expense
                resp_update = await client.put(
                    f"/api/families/{family_id}/expenses/{exp_id}",
                    json={
                        "amount_cents": 2000,
                        "expected_updated_at": exp_updated_at,
                    },
                )
                assert resp_update.status_code == 200, f"member update failed: {resp_update.text}"
                assert resp_update.json()["amount_cents"] == 2000

                # Member CAN delete expense
                resp_delete = await client.delete(f"/api/families/{family_id}/expenses/{exp_id}")
                assert resp_delete.status_code == 200, f"member delete failed: {resp_delete.text}"
        finally:
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 4: RBAC — non-member gets 404 on all expense endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_non_member_gets_404(db_session: AsyncSession) -> None:
    """A user who is not a family member receives 404 on all expense endpoints."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    from app.main import app

    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET

        admin = await create_test_user(db_session, email="admin@nonmember-expenses.test", display_name="Admin")
        outsider = await create_test_user(db_session, email="outsider@nonmember-expenses.test", display_name="Outsider")
        family, _ = await create_test_family(db_session, admin, name="Private Family")
        category = await create_test_category(db_session, family, name="Other")

        # Create an expense as admin for test data
        now = datetime.now(tz=timezone.utc)
        from app.models.expense import Expense

        expense = Expense(
            id=uuid.uuid4(),
            family_id=family.id,
            user_id=admin.id,
            category_id=category.id,
            amount_cents=1000,
            description="Admin expense",
            expense_date=date(2026, 4, 1),
            year_month="2026-04",
            created_at=now,
            updated_at=now,
        )
        db_session.add(expense)
        await db_session.flush()

        app.dependency_overrides[get_db] = _override_get_db(db_session)
        try:
            async with _make_client(app, outsider, db_session) as outsider_client:
                family_id = str(family.id)
                expense_id = str(expense.id)

                # Non-member: POST /expenses -> 404
                resp_create = await outsider_client.post(
                    f"/api/families/{family_id}/expenses",
                    json={
                        "amount_cents": 500,
                        "description": "Unauthorized",
                        "category_id": str(category.id),
                        "expense_date": "2026-04-01",
                    },
                )
                assert resp_create.status_code == 404, (
                    f"expected 404 on create, got {resp_create.status_code}: {resp_create.text}"
                )

                # Non-member: GET /expenses -> 404
                resp_list = await outsider_client.get(f"/api/families/{family_id}/expenses?year_month=2026-04")
                assert resp_list.status_code == 404, (
                    f"expected 404 on list, got {resp_list.status_code}: {resp_list.text}"
                )

                # Non-member: GET /expenses/{id} -> 404
                resp_get = await outsider_client.get(f"/api/families/{family_id}/expenses/{expense_id}")
                assert resp_get.status_code == 404, f"expected 404 on get, got {resp_get.status_code}: {resp_get.text}"

                # Non-member: PUT /expenses/{id} -> 404
                resp_update = await outsider_client.put(
                    f"/api/families/{family_id}/expenses/{expense_id}",
                    json={
                        "amount_cents": 999,
                        "expected_updated_at": now.isoformat(),
                    },
                )
                assert resp_update.status_code == 404, (
                    f"expected 404 on update, got {resp_update.status_code}: {resp_update.text}"
                )

                # Non-member: DELETE /expenses/{id} -> 404
                resp_delete = await outsider_client.delete(f"/api/families/{family_id}/expenses/{expense_id}")
                assert resp_delete.status_code == 404, (
                    f"expected 404 on delete, got {resp_delete.status_code}: {resp_delete.text}"
                )

                # Non-member: GET /budget/summary -> 404
                resp_summary = await outsider_client.get(f"/api/families/{family_id}/budget/summary?month=2026-04")
                assert resp_summary.status_code == 404, (
                    f"expected 404 on budget summary, got {resp_summary.status_code}: {resp_summary.text}"
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
