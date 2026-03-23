"""Tests for user router endpoints: GET/PUT /api/me."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.user import User

# ---------------------------------------------------------------------------
# Helper: override get_current_user with a hardcoded user
# ---------------------------------------------------------------------------


def _make_user(**kwargs) -> User:
    """Build a transient User ORM object for dependency-override tests."""
    defaults = {
        "id": uuid.uuid4(),
        "google_id": f"google_{uuid.uuid4().hex[:8]}",
        "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
        "display_name": "Test User",
        "avatar_url": None,
        "timezone": "America/New_York",
        "created_at": datetime.now(tz=timezone.utc),
        "last_login_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return User(**defaults)


# ---------------------------------------------------------------------------
# GET /api/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_no_cookie_returns_401() -> None:
    """GET /api/me without an access_token cookie returns 401."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/me")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated_returns_user_profile() -> None:
    """GET /api/me with a valid dependency override returns 200 + user profile."""
    from app.main import app

    user = _make_user(display_name="Alice", email="alice@example.com", timezone="America/Chicago")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert body["timezone"] == "America/Chicago"
    assert "id" in body


@pytest.mark.asyncio
async def test_me_response_schema() -> None:
    """GET /api/me response includes all required profile fields."""
    from app.main import app

    user = _make_user(avatar_url="https://example.com/pic.jpg")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    for field in ("id", "email", "display_name", "avatar_url", "timezone"):
        assert field in body, f"Missing field: {field}"
    assert body["avatar_url"] == "https://example.com/pic.jpg"


# ---------------------------------------------------------------------------
# PUT /api/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_update_no_cookie_returns_401() -> None:
    """PUT /api/me without an access_token cookie returns 401."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/me", json={"display_name": "Fail"})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_update_display_name() -> None:
    """PUT /api/me with display_name returns updated profile."""
    from app.main import app

    user = _make_user(display_name="Old Name")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/me", json={"display_name": "New Name"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.json()["display_name"] == "New Name"


@pytest.mark.asyncio
async def test_me_update_timezone() -> None:
    """PUT /api/me with timezone returns updated profile."""
    from app.main import app

    user = _make_user(timezone="America/New_York")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/me", json={"timezone": "America/Chicago"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.json()["timezone"] == "America/Chicago"


@pytest.mark.asyncio
async def test_me_update_both_fields() -> None:
    """PUT /api/me can update display_name and timezone together."""
    from app.main import app

    user = _make_user(display_name="Old", timezone="America/New_York")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/me", json={"display_name": "New", "timezone": "Europe/London"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "New"
    assert body["timezone"] == "Europe/London"


@pytest.mark.asyncio
async def test_me_update_empty_body_no_change() -> None:
    """PUT /api/me with an empty body returns current values unchanged."""
    from app.main import app

    user = _make_user(display_name="Unchanged", timezone="America/Denver")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/me", json={})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Unchanged"
    assert body["timezone"] == "America/Denver"
