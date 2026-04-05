"""API endpoint tests for all monthly goals router endpoints.

Tests cover every goals router endpoint using the authenticated_client fixture
with a NullPool database session override for per-test transaction rollback.

Endpoints tested:
  GET    /api/families/{family_id}/goals                       — list goals (any member)
  PUT    /api/families/{family_id}/goals                       — bulk upsert goals (admin)
  PUT    /api/families/{family_id}/goals/{goal_id}             — update individual goal (admin)
  DELETE /api/families/{family_id}/goals/{goal_id}             — delete goal (admin)
  POST   /api/families/{family_id}/goals/rollover              — copy goals from prior month (admin)
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.category import Category  # noqa: F401 — registers with Base.metadata
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_category,
    create_test_family,
    create_test_monthly_goal,
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
# POST /api/families/{family_id}/goals/rollover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollover_copies_goals_for_admin(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/goals/rollover returns 200 with copied_count for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family, name="Groceries")
    await create_test_monthly_goal(db_session, family, cat, year_month="2026-03", amount_cents=60000)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/goals/rollover",
                json={"source_month": "2026-03", "target_month": "2026-04"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["copied_count"] == 1


@pytest.mark.asyncio
async def test_rollover_returns_zero_when_no_source(db_session: AsyncSession, authenticated_client) -> None:
    """POST rollover returns copied_count=0 when no prior month has goals."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/goals/rollover",
                json={"source_month": "2026-03", "target_month": "2026-04"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["copied_count"] == 0


@pytest.mark.asyncio
async def test_rollover_forbidden_for_non_admin_member(db_session: AsyncSession, authenticated_client) -> None:
    """POST rollover returns 403 when called by a regular member (not admin)."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session, display_name="Member")
    db_session.add(
        FamilyMember(
            id=uuid.uuid4(),
            family_id=family.id,
            user_id=member_user.id,
            role="member",
            joined_at=datetime.now(tz=timezone.utc),
        )
    )
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.post(
                f"/api/families/{family.id}/goals/rollover",
                json={"source_month": "2026-03", "target_month": "2026-04"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rollover_returns_404_for_non_member(db_session: AsyncSession, authenticated_client) -> None:
    """POST rollover returns 404 for a user not in the family (privacy-preserving)."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.post(
                f"/api/families/{family.id}/goals/rollover",
                json={"source_month": "2026-03", "target_month": "2026-04"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollover_copies_multiple_goals(db_session: AsyncSession, authenticated_client) -> None:
    """POST rollover copies all goals from the source month."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat1 = await create_test_category(db_session, family, name="Groceries")
    cat2 = await create_test_category(db_session, family, name="Dining")
    cat3 = await create_test_category(db_session, family, name="Transport")
    await create_test_monthly_goal(db_session, family, cat1, year_month="2026-03", amount_cents=60000)
    await create_test_monthly_goal(db_session, family, cat2, year_month="2026-03", amount_cents=20000)
    await create_test_monthly_goal(db_session, family, cat3, year_month="2026-03", amount_cents=15000)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/goals/rollover",
                json={"source_month": "2026-03", "target_month": "2026-04"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["copied_count"] == 3


# ---------------------------------------------------------------------------
# Helpers for CRUD tests
# ---------------------------------------------------------------------------


async def _make_member(db: AsyncSession, family: Family, user) -> FamilyMember:
    """Insert a member-role FamilyMember for *user* in *family*."""
    member = FamilyMember(
        id=uuid.uuid4(),
        family_id=family.id,
        user_id=user.id,
        role="member",
        joined_at=datetime.now(tz=timezone.utc),
    )
    db.add(member)
    await db.flush()
    return member


# ---------------------------------------------------------------------------
# RBAC: GET /api/families/{family_id}/goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_goals_as_admin(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/goals returns 200 for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)
    await create_test_monthly_goal(db_session, family, cat, year_month="2026-04")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["year_month"] == "2026-04"
    assert len(body["goals"]) == 1
    assert "has_previous_goals" in body


@pytest.mark.asyncio
async def test_list_goals_as_member(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/goals returns 200 for a regular member."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session, display_name="Member")
    await _make_member(db_session, family, member_user)
    cat = await create_test_category(db_session, family)
    await create_test_monthly_goal(db_session, family, cat, year_month="2026-04")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["goals"]) == 1


@pytest.mark.asyncio
async def test_list_goals_as_non_member(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/goals returns 404 for non-members (privacy-preserving)."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC: PUT /api/families/{family_id}/goals (bulk upsert)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_update_as_admin(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals returns 200 for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals",
                json={
                    "year_month": "2026-04",
                    "goals": [
                        {"category_id": str(cat.id), "amount_cents": 50000},
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["year_month"] == "2026-04"
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["deleted"] == 0
    assert len(body["goals"]) == 1


@pytest.mark.asyncio
async def test_bulk_update_as_member(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals returns 403 for a non-admin member."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session, display_name="Member")
    await _make_member(db_session, family, member_user)
    cat = await create_test_category(db_session, family)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals",
                json={
                    "year_month": "2026-04",
                    "goals": [
                        {"category_id": str(cat.id), "amount_cents": 50000},
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RBAC: PUT /api/families/{family_id}/goals/{goal_id} (individual update)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_individual_update_as_admin(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals/{goal_id} returns 200 for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)
    goal = await create_test_monthly_goal(db_session, family, cat, amount_cents=50000)
    initial_version = goal.version  # capture before update mutates the ORM object

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals/{goal.id}",
                json={"amount_cents": 75000, "expected_version": initial_version},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_cents"] == 75000
    assert body["version"] == initial_version + 1


@pytest.mark.asyncio
async def test_individual_update_as_member(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals/{goal_id} returns 403 for non-admin member."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session, display_name="Member")
    await _make_member(db_session, family, member_user)
    cat = await create_test_category(db_session, family)
    goal = await create_test_monthly_goal(db_session, family, cat)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals/{goal.id}",
                json={"amount_cents": 99999, "expected_version": goal.version},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RBAC: DELETE /api/families/{family_id}/goals/{goal_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_as_admin(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/goals/{goal_id} returns 204 for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)
    goal = await create_test_monthly_goal(db_session, family, cat)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.delete(f"/api/families/{family.id}/goals/{goal.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_as_member(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/goals/{goal_id} returns 403 for non-admin member."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    member_user = await create_test_user(db_session, display_name="Member")
    await _make_member(db_session, family, member_user)
    cat = await create_test_category(db_session, family)
    goal = await create_test_monthly_goal(db_session, family, cat)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.delete(f"/api/families/{family.id}/goals/{goal.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Validation: invalid inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_goals_invalid_month_format(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/goals returns 422 for invalid month format."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.get(f"/api/families/{family.id}/goals?month=April-2026")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_goal_negative_amount(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals returns 422 for a negative amount_cents value."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals",
                json={
                    "year_month": "2026-04",
                    "goals": [
                        {"category_id": str(cat.id), "amount_cents": -500},
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Conflict: version mismatch and invalid category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_goal_version_conflict(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals/{goal_id} returns 409 when expected_version is stale."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)
    goal = await create_test_monthly_goal(db_session, family, cat, amount_cents=50000)

    stale_version = goal.version - 1  # intentionally wrong

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals/{goal.id}",
                json={"amount_cents": 60000, "expected_version": stale_version},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bulk_upsert_invalid_category(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/goals returns 404 when a category_id is not in the family."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    fake_cat_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/goals",
                json={
                    "year_month": "2026-04",
                    "goals": [
                        {"category_id": str(fake_cat_id), "amount_cents": 10000},
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration: full CRUD flow and has_previous_goals flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_crud_flow(db_session: AsyncSession, authenticated_client) -> None:
    """Create via bulk, list, update individual, then delete — verifying state at each step."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family, name="Groceries")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            # 1. Bulk-create a goal
            bulk_resp = await client.put(
                f"/api/families/{family.id}/goals",
                json={
                    "year_month": "2026-04",
                    "goals": [{"category_id": str(cat.id), "amount_cents": 50000}],
                },
            )
            assert bulk_resp.status_code == 200
            bulk_body = bulk_resp.json()
            assert bulk_body["created"] == 1
            goal_id = bulk_body["goals"][0]["id"]
            goal_version = bulk_body["goals"][0]["version"]

            # 2. List goals and confirm presence
            list_resp = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
            assert list_resp.status_code == 200
            list_body = list_resp.json()
            assert len(list_body["goals"]) == 1
            assert list_body["goals"][0]["id"] == goal_id

            # 3. Update the individual goal
            update_resp = await client.put(
                f"/api/families/{family.id}/goals/{goal_id}",
                json={"amount_cents": 75000, "expected_version": goal_version},
            )
            assert update_resp.status_code == 200
            update_body = update_resp.json()
            assert update_body["amount_cents"] == 75000
            assert update_body["version"] == goal_version + 1

            # 4. Delete the goal
            delete_resp = await client.delete(f"/api/families/{family.id}/goals/{goal_id}")
            assert delete_resp.status_code == 204

            # 5. Confirm it's gone
            final_list = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
            assert final_list.status_code == 200
            assert len(final_list.json()["goals"]) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_list_goals_has_previous_goals_flag(db_session: AsyncSession, authenticated_client) -> None:
    """has_previous_goals is True when a prior month has goals but the requested month does not."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family)
    # Insert goals in March so April sees has_previous_goals=True
    await create_test_monthly_goal(db_session, family, cat, year_month="2026-03")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.get(f"/api/families/{family.id}/goals?month=2026-04")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_previous_goals"] is True
    assert len(body["goals"]) == 0
