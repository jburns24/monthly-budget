"""API tests for POST /api/families/{family_id}/categories/suggest."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.dependencies import get_llm_client
from tests.conftest import _TEST_JWT_SECRET, create_test_category, create_test_family, create_test_user


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
def patch_jwt_secret():
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


@pytest.fixture(autouse=True)
def overrides(db_session: AsyncSession):
    """Real DB session, a dummy LLM client, the decision mock on, and an open rate limiter."""
    from app.main import app

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_llm_client] = lambda: MagicMock()
    with (
        patch("app.services.category_classifier.settings.decision_mock", True),
        patch("app.services.category_classifier.settings.decision_mock_scenario", "success"),
        patch(
            "app.routers.categories.rate_limiter.check_and_increment_category_suggest",
            new=AsyncMock(return_value=(True, 1)),
        ) as limiter,
    ):
        yield limiter
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_llm_client, None)


def _url(family_id) -> str:
    return f"/api/families/{family_id}/categories/suggest"


async def test_member_gets_suggestion(db_session: AsyncSession, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    cat = await create_test_category(db_session, family, name="Dining", sort_order=0)
    await create_test_category(db_session, family, name="Bills", sort_order=1)

    async with authenticated_client(user) as client:
        resp = await client.post(_url(family.id), json={"description": "Starbucks latte"})

    assert resp.status_code == 200
    assert resp.json() == {"category_id": str(cat.id), "category_name": "Dining"}


async def test_low_confidence_returns_nulls(db_session: AsyncSession, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    await create_test_category(db_session, family, name="Dining")

    with patch("app.services.category_classifier.settings.decision_mock_scenario", "low_confidence"):
        async with authenticated_client(user) as client:
            resp = await client.post(_url(family.id), json={"description": "zzzz"})

    assert resp.status_code == 200
    assert resp.json() == {"category_id": None, "category_name": None}


async def test_trigram_fallback_on_model_error(db_session: AsyncSession, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    await create_test_category(db_session, family, name="Bills", sort_order=0)
    coffee = await create_test_category(db_session, family, name="Coffee", sort_order=1)

    with patch("app.services.category_classifier.settings.decision_mock_scenario", "api_error"):
        async with authenticated_client(user) as client:
            resp = await client.post(_url(family.id), json={"description": "coffee"})

    assert resp.status_code == 200
    assert resp.json() == {"category_id": str(coffee.id), "category_name": "Coffee"}


async def test_inactive_categories_are_never_suggested(db_session: AsyncSession, authenticated_client) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    await create_test_category(db_session, family, name="Archived", is_active=False, sort_order=0)
    active = await create_test_category(db_session, family, name="Dining", sort_order=1)

    async with authenticated_client(user) as client:
        resp = await client.post(_url(family.id), json={"description": "lunch"})

    assert resp.json()["category_id"] == str(active.id)


async def test_non_member_gets_404(db_session: AsyncSession, authenticated_client) -> None:
    owner = await create_test_user(db_session, display_name="Owner")
    family, _ = await create_test_family(db_session, owner)
    outsider = await create_test_user(db_session, display_name="Outsider")

    async with authenticated_client(outsider) as client:
        resp = await client.post(_url(family.id), json={"description": "lunch"})

    assert resp.status_code == 404


@pytest.mark.parametrize("description", ["", "x" * 201])
async def test_description_length_validated(db_session: AsyncSession, authenticated_client, description: str) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    async with authenticated_client(user) as client:
        resp = await client.post(_url(family.id), json={"description": description})

    assert resp.status_code == 422


async def test_rate_limited_returns_429(db_session: AsyncSession, authenticated_client, overrides) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    overrides.return_value = (False, 501)

    async with authenticated_client(user) as client:
        resp = await client.post(_url(family.id), json={"description": "lunch"})

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "86400"
