"""API endpoint tests for all category routes.

Tests cover every category router endpoint using the authenticated_client fixture
with a NullPool database session override for per-test transaction rollback.

Endpoints tested:
  GET    /api/families/{family_id}/categories                          — list active categories
  POST   /api/families/{family_id}/categories                          — create category (admin)
  PUT    /api/families/{family_id}/categories/{category_id}            — update category (admin)
  DELETE /api/families/{family_id}/categories/{category_id}            — delete category (admin)
  POST   /api/families/{family_id}/categories/seed                     — seed defaults (admin)
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.category import Category  # noqa: F401 — registers with Base.metadata
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import _TEST_JWT_SECRET, create_test_category, create_test_family, create_test_user

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
# GET /api/families/{family_id}/categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_categories_returns_active_for_member(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/categories returns only active categories for any family member."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    active_cat = await create_test_category(db_session, family, name="Groceries", is_active=True)
    await create_test_category(db_session, family, name="Archived", is_active=False)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/categories")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    names = [c["name"] for c in body]
    assert "Groceries" in names
    assert "Archived" not in names
    assert body[0]["id"] == str(active_cat.id)


@pytest.mark.asyncio
async def test_list_categories_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/categories returns 404 for non-members (privacy-preserving)."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.get(f"/api/families/{family.id}/categories")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_categories_empty_list_when_none(db_session: AsyncSession, authenticated_client) -> None:
    """GET /api/families/{id}/categories returns an empty list when no active categories exist."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/categories")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_category_returns_201_for_admin(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories with valid body returns 201 for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/categories",
                json={"name": "Dining Out", "icon": "fork", "sort_order": 2},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Dining Out"
    assert body["icon"] == "fork"
    assert body["sort_order"] == 2
    assert body["is_active"] is True
    assert "id" in body
    assert body["family_id"] == str(family.id)


@pytest.mark.asyncio
async def test_create_category_returns_403_for_non_admin(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories returns 403 for a non-admin member."""
    from datetime import datetime, timezone

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
                f"/api/families/{family.id}/categories",
                json={"name": "Groceries"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_category_duplicate_name_returns_409(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories returns 409 when name already exists."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    await create_test_category(db_session, family, name="Groceries")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(
                f"/api/families/{family.id}/categories",
                json={"name": "Groceries"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# PUT /api/families/{family_id}/categories/{category_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_category_updates_fields_for_admin(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/categories/{cat_id} updates the category for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family, name="Old Name", icon="star", sort_order=1)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/categories/{cat.id}",
                json={"name": "New Name", "icon": "moon", "sort_order": 5},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["icon"] == "moon"
    assert body["sort_order"] == 5
    assert body["id"] == str(cat.id)


@pytest.mark.asyncio
async def test_update_category_not_found_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/categories/{cat_id} returns 404 for non-existent category."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    fake_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.put(
                f"/api/families/{family.id}/categories/{fake_id}",
                json={"name": "Ghost"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_category_returns_403_for_non_admin(db_session: AsyncSession, authenticated_client) -> None:
    """PUT /api/families/{id}/categories/{cat_id} returns 403 for non-admin member."""
    from datetime import datetime, timezone

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
    cat = await create_test_category(db_session, family, name="Protected")
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.put(
                f"/api/families/{family.id}/categories/{cat.id}",
                json={"name": "Hacked"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/families/{family_id}/categories/{category_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_category_hard_deletes_for_admin(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/categories/{cat_id} hard-deletes for admin when no expenses."""
    from sqlalchemy import select

    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    cat = await create_test_category(db_session, family, name="ToDelete")
    cat_id = cat.id

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.delete(f"/api/families/{family.id}/categories/{cat_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert "message" in body

    # Verify row is gone
    result = await db_session.execute(select(Category).where(Category.id == cat_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_category_returns_403_for_non_admin(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/categories/{cat_id} returns 403 for non-admin member."""
    from datetime import datetime, timezone

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
    cat = await create_test_category(db_session, family, name="Protected")
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(member_user) as client:
            resp = await client.delete(f"/api/families/{family.id}/categories/{cat.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_category_not_found_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """DELETE /api/families/{id}/categories/{cat_id} returns 404 for non-existent category."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    fake_id = uuid.uuid4()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.delete(f"/api/families/{family.id}/categories/{fake_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/categories/seed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_categories_creates_six_defaults(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories/seed creates 6 default categories for admin."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.post(f"/api/families/{family.id}/categories/seed")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 6
    assert "message" in body
    assert "6" in body["message"]


@pytest.mark.asyncio
async def test_seed_categories_idempotent(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories/seed is idempotent: second call creates 0."""
    from app.main import app

    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            first = await client.post(f"/api/families/{family.id}/categories/seed")
            second = await client.post(f"/api/families/{family.id}/categories/seed")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created_count"] == 6
    assert second.json()["created_count"] == 0


@pytest.mark.asyncio
async def test_seed_categories_returns_403_for_non_admin(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories/seed returns 403 for non-admin member."""
    from datetime import datetime, timezone

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
            resp = await client.post(f"/api/families/{family.id}/categories/seed")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_seed_categories_non_member_returns_404(db_session: AsyncSession, authenticated_client) -> None:
    """POST /api/families/{id}/categories/seed returns 404 for non-member (privacy-preserving)."""
    from app.main import app

    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(outsider) as client:
            resp = await client.post(f"/api/families/{family.id}/categories/seed")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
