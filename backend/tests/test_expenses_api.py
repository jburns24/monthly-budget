"""API endpoint tests for all expense routes.

Tests cover every expense router endpoint using the authenticated_client fixture
with a NullPool database session override for per-test transaction rollback.

Endpoints tested:
  GET    /api/families/{family_id}/expenses                             — list expenses by month
  POST   /api/families/{family_id}/expenses                            — create expense (any member)
  GET    /api/families/{family_id}/expenses/{expense_id}               — get single expense
  PUT    /api/families/{family_id}/expenses/{expense_id}               — update expense
  DELETE /api/families/{family_id}/expenses/{expense_id}               — delete expense
  GET    /api/families/{family_id}/budget/summary                      — budget summary
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.category import Category  # noqa: F401 — registers with Base.metadata
from app.models.expense import Expense  # noqa: F401 — registers with Base.metadata
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_category,
    create_test_expense,
    create_test_family,
    create_test_user,
)

# ---------------------------------------------------------------------------
# NullPool db_session fixture — per-test transaction rollback
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# JWT patch fixture — ensures decode_token uses the same secret as the test JWTs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    """Patch app.services.jwt_service.settings so decode_token uses _TEST_JWT_SECRET."""
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_expense_returns_201_for_member(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/expenses with valid body returns 201 for any family member."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries", is_active=True)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(
                f"/api/families/{family.id}/expenses",
                json={
                    "amount_cents": 2500,
                    "description": "Weekly groceries",
                    "category_id": str(category.id),
                    "expense_date": "2026-04-01",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    body = resp.json()
    assert body["amount_cents"] == 2500
    assert body["description"] == "Weekly groceries"
    assert body["family_id"] == str(family.id)
    assert body["category"]["id"] == str(category.id)
    assert body["category"]["name"] == "Groceries"
    assert body["expense_date"] == "2026-04-01"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


@pytest.mark.asyncio
async def test_create_expense_validates_amount_greater_than_zero(
    db_session: AsyncSession, authenticated_client
) -> None:
    """POST /api/families/{id}/expenses returns 422 when amount_cents <= 0."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Bills", is_active=True)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(
                f"/api/families/{family.id}/expenses",
                json={
                    "amount_cents": 0,
                    "description": "Zero cost",
                    "category_id": str(category.id),
                    "expense_date": "2026-04-01",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_expense_validates_amount_negative(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/expenses returns 422 when amount_cents is negative."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Dining", is_active=True)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(
                f"/api/families/{family.id}/expenses",
                json={
                    "amount_cents": -100,
                    "description": "Negative amount",
                    "category_id": str(category.id),
                    "expense_date": "2026-04-01",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_expense_validates_inactive_category(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/expenses returns 400 when category is inactive."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    inactive_cat = await create_test_category(db_session, family, name="Archived", is_active=False)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(
                f"/api/families/{family.id}/expenses",
                json={
                    "amount_cents": 1000,
                    "description": "Using archived category",
                    "category_id": str(inactive_cat.id),
                    "expense_date": "2026-04-01",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_expense_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/expenses returns 404 for non-member users."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family, name="Transport")
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.post(
                f"/api/families/{family.id}/expenses",
                json={
                    "amount_cents": 1000,
                    "description": "Unauthorized expense",
                    "category_id": str(category.id),
                    "expense_date": "2026-04-01",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_expenses_by_month(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses?year_month= returns expenses for that month."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")

    # Create two expenses in April and one in March
    await create_test_expense(
        db_session, family, user, category, amount_cents=1000, expense_date=date(2026, 4, 1), year_month="2026-04"
    )
    await create_test_expense(
        db_session, family, user, category, amount_cents=2000, expense_date=date(2026, 4, 15), year_month="2026-04"
    )
    await create_test_expense(
        db_session, family, user, category, amount_cents=500, expense_date=date(2026, 3, 15), year_month="2026-03"
    )

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/expenses?year_month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    assert len(body["expenses"]) == 2
    assert body["page"] == 1
    assert body["per_page"] == 50
    amounts = {e["amount_cents"] for e in body["expenses"]}
    assert amounts == {1000, 2000}


@pytest.mark.asyncio
async def test_list_expenses_paginates_correctly(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses?year_month=&page=&per_page= paginates results."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Dining")

    # Create 5 expenses in the same month
    for i in range(1, 6):
        await create_test_expense(
            db_session,
            family,
            user,
            category,
            amount_cents=i * 100,
            expense_date=date(2026, 4, i),
            year_month="2026-04",
        )

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp_page1 = await client.get(f"/api/families/{family.id}/expenses?year_month=2026-04&per_page=2&page=1")
            resp_page2 = await client.get(f"/api/families/{family.id}/expenses?year_month=2026-04&per_page=2&page=2")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp_page1.status_code == 200
    body1 = resp_page1.json()
    assert body1["total_count"] == 5
    assert len(body1["expenses"]) == 2
    assert body1["page"] == 1
    assert body1["per_page"] == 2

    assert resp_page2.status_code == 200
    body2 = resp_page2.json()
    assert body2["total_count"] == 5
    assert len(body2["expenses"]) == 2
    assert body2["page"] == 2

    # Ensure no duplicate IDs across pages
    ids_page1 = {e["id"] for e in body1["expenses"]}
    ids_page2 = {e["id"] for e in body2["expenses"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.asyncio
async def test_list_expenses_filters_by_category(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses?year_month=&category_id= filters by category."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat_groceries = await create_test_category(db_session, family, name="Groceries")
    cat_dining = await create_test_category(db_session, family, name="Dining")

    await create_test_expense(
        db_session, family, user, cat_groceries, amount_cents=1500, expense_date=date(2026, 4, 5), year_month="2026-04"
    )
    await create_test_expense(
        db_session, family, user, cat_dining, amount_cents=3000, expense_date=date(2026, 4, 10), year_month="2026-04"
    )

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(
                f"/api/families/{family.id}/expenses?year_month=2026-04&category_id={cat_groceries.id}"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert body["expenses"][0]["amount_cents"] == 1500
    assert body["expenses"][0]["category"]["name"] == "Groceries"


@pytest.mark.asyncio
async def test_list_expenses_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses returns 404 for non-member users."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.get(f"/api/families/{family.id}/expenses?year_month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/expenses/{expense_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_expense_returns_200(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses/{expense_id} returns the expense with relationships."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Bills")
    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        amount_cents=7500,
        description="Electricity bill",
        expense_date=date(2026, 4, 3),
        year_month="2026-04",
    )

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/expenses/{expense.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(expense.id)
    assert body["amount_cents"] == 7500
    assert body["description"] == "Electricity bill"
    assert body["category"]["name"] == "Bills"
    assert body["family_id"] == str(family.id)


@pytest.mark.asyncio
async def test_get_expense_not_found_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/expenses/{expense_id} returns 404 for non-existent expense."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    fake_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/expenses/{fake_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/families/{family_id}/expenses/{expense_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_expense_updates_fields(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/expenses/{expense_id} updates amount and description."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Transport")
    expense = await create_test_expense(
        db_session,
        family,
        user,
        category,
        amount_cents=500,
        description="Bus ticket",
        expense_date=date(2026, 4, 5),
        year_month="2026-04",
    )

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/expenses/{expense.id}",
                json={
                    "amount_cents": 1200,
                    "description": "Train ticket",
                    "expected_updated_at": expense.updated_at.isoformat(),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_cents"] == 1200
    assert body["description"] == "Train ticket"
    assert body["id"] == str(expense.id)


@pytest.mark.asyncio
async def test_update_expense_returns_409_on_stale_updated_at(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/expenses/{expense_id} returns 409 when expected_updated_at is stale."""
    from datetime import datetime, timezone

    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Entertainment")
    expense = await create_test_expense(
        db_session, family, user, category, amount_cents=2000, expense_date=date(2026, 4, 10), year_month="2026-04"
    )

    # Use a stale timestamp (different from the actual updated_at)
    stale_ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/expenses/{expense.id}",
                json={
                    "amount_cents": 3000,
                    "expected_updated_at": stale_ts.isoformat(),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_expense_not_found_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/expenses/{expense_id} returns 404 for non-existent expense."""
    from datetime import datetime, timezone

    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    fake_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/expenses/{fake_id}",
                json={
                    "amount_cents": 500,
                    "expected_updated_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/families/{family_id}/expenses/{expense_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_expense_removes_record(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/expenses/{expense_id} hard-deletes the expense."""
    from sqlalchemy import select

    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Other")
    expense = await create_test_expense(
        db_session, family, user, category, amount_cents=999, expense_date=date(2026, 4, 20), year_month="2026-04"
    )
    expense_id = expense.id

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.delete(f"/api/families/{family.id}/expenses/{expense_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body

    # Verify row is gone
    result = await db_session.execute(select(Expense).where(Expense.id == expense_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_expense_not_found_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/expenses/{expense_id} returns 404 for non-existent expense."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    fake_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.delete(f"/api/families/{family.id}/expenses/{fake_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_expense_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/expenses/{expense_id} returns 404 for non-member users."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family, name="Bills")
    expense = await create_test_expense(
        db_session, family, owner, category, amount_cents=500, expense_date=date(2026, 4, 1), year_month="2026-04"
    )
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.delete(f"/api/families/{family.id}/expenses/{expense.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/budget/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_summary_returns_correct_aggregation(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/budget/summary returns accurate aggregation per category."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat_groceries = await create_test_category(db_session, family, name="Groceries", sort_order=0)
    cat_dining = await create_test_category(db_session, family, name="Dining", sort_order=1)

    # Create expenses for April 2026
    await create_test_expense(
        db_session, family, user, cat_groceries, amount_cents=3000, expense_date=date(2026, 4, 5), year_month="2026-04"
    )
    await create_test_expense(
        db_session, family, user, cat_groceries, amount_cents=2000, expense_date=date(2026, 4, 10), year_month="2026-04"
    )
    await create_test_expense(
        db_session, family, user, cat_dining, amount_cents=5000, expense_date=date(2026, 4, 15), year_month="2026-04"
    )

    # Add a goal for Groceries: 10000 cents
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    goal = MonthlyGoal(
        id=uuid.uuid4(),
        family_id=family.id,
        category_id=cat_groceries.id,
        year_month="2026-04",
        amount_cents=10000,
        created_at=now,
        updated_at=now,
    )
    db_session.add(goal)
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/budget/summary?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["year_month"] == "2026-04"
    assert body["total_spent_cents"] == 10000  # 3000 + 2000 + 5000

    cats = {c["category_name"]: c for c in body["categories"]}
    assert "Groceries" in cats
    assert "Dining" in cats

    groceries_summary = cats["Groceries"]
    assert groceries_summary["spent_cents"] == 5000  # 3000 + 2000
    assert groceries_summary["goal_cents"] == 10000
    assert groceries_summary["percentage"] == 0.5
    assert groceries_summary["status"] == "green"

    dining_summary = cats["Dining"]
    assert dining_summary["spent_cents"] == 5000
    assert dining_summary["goal_cents"] is None
    assert dining_summary["status"] == "none"


@pytest.mark.asyncio
async def test_budget_summary_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/budget/summary returns 404 for non-member users."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.get(f"/api/families/{family.id}/budget/summary?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
