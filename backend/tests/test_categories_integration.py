"""Integration tests for category lifecycle and RBAC.

Tests cover:
- Full category lifecycle: create -> list -> update -> delete (archive)
- Seed then CRUD: seed defaults -> verify 6 categories -> create custom -> update -> delete
- RBAC enforcement: admin can create/update/delete; member can only read; non-member gets 404
- Cross-family isolation: categories from one family are not visible to another family's member

Each test uses the full HTTP API layer with authenticated clients and per-test DB rollback.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.category import Category  # noqa: F401 — registers with Base.metadata
from app.models.family import Family  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import _TEST_JWT_SECRET, create_test_family, create_test_user

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
    from datetime import datetime, timezone

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
# Local helper: create_test_category (avoids dependency on conftest additions)
# ---------------------------------------------------------------------------


async def _create_test_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    name: str = "Test Category",
    icon: str | None = None,
    sort_order: int = 0,
) -> Category:
    """Insert a Category record directly into the DB and return the ORM instance."""
    category = Category(
        id=uuid.uuid4(),
        family_id=family_id,
        name=name,
        icon=icon,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


# ---------------------------------------------------------------------------
# Test 1: Full category lifecycle — create -> list -> update -> delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_category_lifecycle(db_session: AsyncSession) -> None:
    """Full category lifecycle through the HTTP API.

    Steps:
    1. Admin creates a category (POST /api/families/{id}/categories) — expect 201
    2. Admin lists categories (GET /api/families/{id}/categories) — category appears
    3. Admin updates the category name (PUT /api/families/{id}/categories/{cat_id}) — expect 200
    4. Admin deletes the category (DELETE /api/families/{id}/categories/{cat_id}) — expect 200, deleted=True
    5. Admin lists categories again — list is empty
    """
    from app.main import app

    admin = await create_test_user(db_session, email="admin@lifecycle.test", display_name="Admin")
    family, _ = await create_test_family(db_session, admin, name="Lifecycle Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin, db_session) as client:
            family_id = str(family.id)

            # Step 1: Create category
            resp1 = await client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Groceries", "icon": "🛒", "sort_order": 0},
            )
            assert resp1.status_code == 201, f"create failed: {resp1.text}"
            cat_data = resp1.json()
            assert cat_data["name"] == "Groceries"
            assert cat_data["icon"] == "🛒"
            assert cat_data["sort_order"] == 0
            assert cat_data["is_active"] is True
            assert cat_data["family_id"] == family_id
            category_id = cat_data["id"]

            # Step 2: List categories — new category appears
            resp2 = await client.get(f"/api/families/{family_id}/categories")
            assert resp2.status_code == 200, f"list failed: {resp2.text}"
            categories = resp2.json()
            assert len(categories) == 1
            assert categories[0]["id"] == category_id
            assert categories[0]["name"] == "Groceries"

            # Step 3: Update category name
            resp3 = await client.put(
                f"/api/families/{family_id}/categories/{category_id}",
                json={"name": "Groceries & Food"},
            )
            assert resp3.status_code == 200, f"update failed: {resp3.text}"
            updated = resp3.json()
            assert updated["name"] == "Groceries & Food"
            assert updated["id"] == category_id

            # Step 4: Delete category (hard delete, no expenses)
            resp4 = await client.delete(f"/api/families/{family_id}/categories/{category_id}")
            assert resp4.status_code == 200, f"delete failed: {resp4.text}"
            del_data = resp4.json()
            assert del_data["deleted"] is True
            assert del_data["archived"] is False

            # Step 5: List categories — now empty
            resp5 = await client.get(f"/api/families/{family_id}/categories")
            assert resp5.status_code == 200, f"list after delete failed: {resp5.text}"
            assert resp5.json() == []
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 2: Seed then CRUD — seed defaults, verify 6, create custom, update, delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_then_crud_lifecycle(db_session: AsyncSession) -> None:
    """Seed default categories then perform CRUD operations.

    Steps:
    1. Seed default categories (POST /api/families/{id}/categories/seed) — expect 200, created_count=6
    2. List categories — exactly 6 categories present with expected names
    3. Create a custom category — total becomes 7
    4. Update one seeded category's icon
    5. Delete the custom category — total goes back to 6
    6. Seed again — idempotent, created_count=0
    """
    from app.main import app

    admin = await create_test_user(db_session, email="admin@seed.test", display_name="Seeder")
    family, _ = await create_test_family(db_session, admin, name="Seed Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin, db_session) as client:
            family_id = str(family.id)

            # Step 1: Seed default categories
            resp1 = await client.post(f"/api/families/{family_id}/categories/seed")
            assert resp1.status_code == 200, f"seed failed: {resp1.text}"
            seed_data = resp1.json()
            assert seed_data["created_count"] == 6
            assert "6" in seed_data["message"]

            # Step 2: List — verify 6 default categories
            resp2 = await client.get(f"/api/families/{family_id}/categories")
            assert resp2.status_code == 200, f"list failed: {resp2.text}"
            categories = resp2.json()
            assert len(categories) == 6
            names = {c["name"] for c in categories}
            assert names == {"Groceries", "Dining", "Transport", "Entertainment", "Bills", "Other"}

            # Step 3: Create a custom category
            resp3 = await client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Savings", "icon": "💰", "sort_order": 10},
            )
            assert resp3.status_code == 201, f"create custom failed: {resp3.text}"
            custom_id = resp3.json()["id"]

            resp3b = await client.get(f"/api/families/{family_id}/categories")
            assert len(resp3b.json()) == 7

            # Step 4: Update one seeded category's icon
            groceries = next(c for c in categories if c["name"] == "Groceries")
            resp4 = await client.put(
                f"/api/families/{family_id}/categories/{groceries['id']}",
                json={"icon": "🥦"},
            )
            assert resp4.status_code == 200, f"update icon failed: {resp4.text}"
            assert resp4.json()["icon"] == "🥦"
            assert resp4.json()["name"] == "Groceries"  # name unchanged

            # Step 5: Delete custom category — back to 6
            resp5 = await client.delete(f"/api/families/{family_id}/categories/{custom_id}")
            assert resp5.status_code == 200, f"delete custom failed: {resp5.text}"
            assert resp5.json()["deleted"] is True

            resp5b = await client.get(f"/api/families/{family_id}/categories")
            assert len(resp5b.json()) == 6

            # Step 6: Seed again — idempotent
            resp6 = await client.post(f"/api/families/{family_id}/categories/seed")
            assert resp6.status_code == 200, f"re-seed failed: {resp6.text}"
            assert resp6.json()["created_count"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 3: RBAC — admin can perform all operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_admin_can_create_update_delete(db_session: AsyncSession) -> None:
    """Admin members may create, update, and delete categories."""
    from app.main import app

    admin = await create_test_user(db_session, email="admin@rbac.test", display_name="Admin")
    family, _ = await create_test_family(db_session, admin, name="RBAC Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin, db_session) as client:
            family_id = str(family.id)

            # Admin can create
            resp_create = await client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Admin Category", "sort_order": 0},
            )
            assert resp_create.status_code == 201, f"admin create failed: {resp_create.text}"
            cat_id = resp_create.json()["id"]

            # Admin can update
            resp_update = await client.put(
                f"/api/families/{family_id}/categories/{cat_id}",
                json={"name": "Admin Category Updated"},
            )
            assert resp_update.status_code == 200, f"admin update failed: {resp_update.text}"

            # Admin can seed
            resp_seed = await client.post(f"/api/families/{family_id}/categories/seed")
            assert resp_seed.status_code == 200, f"admin seed failed: {resp_seed.text}"

            # Admin can delete
            resp_delete = await client.delete(f"/api/families/{family_id}/categories/{cat_id}")
            assert resp_delete.status_code == 200, f"admin delete failed: {resp_delete.text}"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 4: RBAC — member (non-admin) can read but not write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_member_can_read_not_write(db_session: AsyncSession) -> None:
    """Family members with the 'member' role can list categories but cannot create, update, or delete."""
    from app.main import app

    admin = await create_test_user(db_session, email="admin@member-rbac.test", display_name="Admin")
    member_user = await create_test_user(db_session, email="member@member-rbac.test", display_name="Member")
    family, _ = await create_test_family(db_session, admin, name="Member RBAC Family")

    # Add member_user as a 'member' (not admin)
    from datetime import datetime, timezone

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

    # Create a category as admin for later tests
    category = await _create_test_category(db_session, family.id, name="Utilities")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, member_user, db_session) as member_client:
            family_id = str(family.id)

            # Member CAN list categories
            resp_list = await member_client.get(f"/api/families/{family_id}/categories")
            assert resp_list.status_code == 200, f"member list failed: {resp_list.text}"
            assert any(c["name"] == "Utilities" for c in resp_list.json())

            # Member CANNOT create categories
            resp_create = await member_client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Forbidden Category"},
            )
            assert resp_create.status_code == 403, (
                f"expected 403 on create, got {resp_create.status_code}: {resp_create.text}"
            )

            # Member CANNOT update categories
            resp_update = await member_client.put(
                f"/api/families/{family_id}/categories/{category.id}",
                json={"name": "Forbidden Update"},
            )
            assert resp_update.status_code == 403, (
                f"expected 403 on update, got {resp_update.status_code}: {resp_update.text}"
            )

            # Member CANNOT delete categories
            resp_delete = await member_client.delete(f"/api/families/{family_id}/categories/{category.id}")
            assert resp_delete.status_code == 403, (
                f"expected 403 on delete, got {resp_delete.status_code}: {resp_delete.text}"
            )

            # Member CANNOT seed categories
            resp_seed = await member_client.post(f"/api/families/{family_id}/categories/seed")
            assert resp_seed.status_code == 403, f"expected 403 on seed, got {resp_seed.status_code}: {resp_seed.text}"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 5: RBAC — non-member user gets 404 (family not found)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_non_member_gets_404(db_session: AsyncSession) -> None:
    """A user who is not a member of the family receives 404 on all category endpoints.

    The 404 prevents leaking whether the family exists.
    """
    from app.main import app

    admin = await create_test_user(db_session, email="admin@nonmember.test", display_name="Admin")
    outsider = await create_test_user(db_session, email="outsider@nonmember.test", display_name="Outsider")
    family, _ = await create_test_family(db_session, admin, name="Secret Family")

    # Pre-create a category so we have a real category_id to test with
    category = await _create_test_category(db_session, family.id, name="Private Category")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, outsider, db_session) as outsider_client:
            family_id = str(family.id)
            cat_id = str(category.id)

            # List — 404 for non-member
            resp_list = await outsider_client.get(f"/api/families/{family_id}/categories")
            assert resp_list.status_code == 404, f"expected 404 on list, got {resp_list.status_code}"

            # Create — 404 for non-member
            resp_create = await outsider_client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Hacked Category"},
            )
            assert resp_create.status_code == 404, f"expected 404 on create, got {resp_create.status_code}"

            # Update — 404 for non-member
            resp_update = await outsider_client.put(
                f"/api/families/{family_id}/categories/{cat_id}",
                json={"name": "Hacked Update"},
            )
            assert resp_update.status_code == 404, f"expected 404 on update, got {resp_update.status_code}"

            # Delete — 404 for non-member
            resp_delete = await outsider_client.delete(f"/api/families/{family_id}/categories/{cat_id}")
            assert resp_delete.status_code == 404, f"expected 404 on delete, got {resp_delete.status_code}"

            # Seed — 404 for non-member
            resp_seed = await outsider_client.post(f"/api/families/{family_id}/categories/seed")
            assert resp_seed.status_code == 404, f"expected 404 on seed, got {resp_seed.status_code}"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 6: Cross-family isolation — member of family A cannot see family B's categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_family_isolation(db_session: AsyncSession) -> None:
    """Categories from one family are not accessible to members of another family.

    Family A admin has categories. Family B admin tries to access them — gets 404.
    """
    from app.main import app

    admin_a = await create_test_user(db_session, email="admin_a@isolation.test", display_name="Admin A")
    admin_b = await create_test_user(db_session, email="admin_b@isolation.test", display_name="Admin B")
    family_a, _ = await create_test_family(db_session, admin_a, name="Family A")
    family_b, _ = await create_test_family(db_session, admin_b, name="Family B")

    # Create a category in Family A
    cat_a = await _create_test_category(db_session, family_a.id, name="Family A Category")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin_b, db_session) as client_b:
            family_a_id = str(family_a.id)
            cat_a_id = str(cat_a.id)

            # Admin B cannot list Family A's categories
            resp_list = await client_b.get(f"/api/families/{family_a_id}/categories")
            assert resp_list.status_code == 404, f"expected 404 on cross-family list, got {resp_list.status_code}"

            # Admin B cannot update Family A's category
            resp_update = await client_b.put(
                f"/api/families/{family_a_id}/categories/{cat_a_id}",
                json={"name": "Hijacked"},
            )
            assert resp_update.status_code == 404, f"expected 404 on cross-family update, got {resp_update.status_code}"

            # Admin B cannot delete Family A's category
            resp_delete = await client_b.delete(f"/api/families/{family_a_id}/categories/{cat_a_id}")
            assert resp_delete.status_code == 404, f"expected 404 on cross-family delete, got {resp_delete.status_code}"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 7: Duplicate category name rejected with 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_category_name_rejected(db_session: AsyncSession) -> None:
    """Creating a category with a name that already exists in the family returns 409."""
    from app.main import app

    admin = await create_test_user(db_session, email="admin@dup.test", display_name="Admin")
    family, _ = await create_test_family(db_session, admin, name="Dup Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin, db_session) as client:
            family_id = str(family.id)

            # Create first category
            resp1 = await client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Groceries"},
            )
            assert resp1.status_code == 201, f"first create failed: {resp1.text}"

            # Attempt duplicate
            resp2 = await client.post(
                f"/api/families/{family_id}/categories",
                json={"name": "Groceries"},
            )
            assert resp2.status_code == 409, f"expected 409 on duplicate, got {resp2.status_code}: {resp2.text}"
            assert "Groceries" in resp2.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 8: Update non-existent category returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_nonexistent_category_returns_404(db_session: AsyncSession) -> None:
    """Updating a category that does not exist returns 404."""
    from app.main import app

    admin = await create_test_user(db_session, email="admin@notfound.test", display_name="Admin")
    family, _ = await create_test_family(db_session, admin, name="NotFound Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with _make_client(app, admin, db_session) as client:
            family_id = str(family.id)
            ghost_id = str(uuid.uuid4())

            resp = await client.put(
                f"/api/families/{family_id}/categories/{ghost_id}",
                json={"name": "Ghost Category"},
            )
            assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 9: Unauthenticated requests are rejected with 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(db_session: AsyncSession) -> None:
    """Requests without a valid JWT cookie are rejected with 401."""
    from app.main import app

    admin = await create_test_user(db_session, email="admin@unauth.test", display_name="Admin")
    family, _ = await create_test_family(db_session, admin, name="Unauth Family")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as anon_client:
            family_id = str(family.id)

            resp = await anon_client.get(f"/api/families/{family_id}/categories")
            assert resp.status_code == 401, f"expected 401 for unauthenticated request, got {resp.status_code}"
    finally:
        app.dependency_overrides.pop(get_db, None)
