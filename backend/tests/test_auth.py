"""Tests for auth router endpoints: /api/auth/callback, /refresh, /logout."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.refresh_token_blacklist import RefreshTokenBlacklist
from tests.conftest import _TEST_JWT_SECRET, _make_jwt, create_test_user

_JWT_SECRET = _TEST_JWT_SECRET


# ---------------------------------------------------------------------------
# NullPool db_session fixture — yields a real session but rolls back after test
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
# Override get_db to share the test session with the FastAPI app
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    """Return an async generator that yields *session* as the app DB dependency."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# /api/auth/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_success_new_user(db_session: AsyncSession) -> None:
    """POST /api/auth/callback with mocked Google returns 200 and sets cookies."""
    from app.main import app

    google_info: dict[str, Any] = {
        "sub": f"google_{uuid.uuid4().hex[:8]}",
        "email": f"new_{uuid.uuid4().hex[:6]}@example.com",
        "name": "New User",
        "picture": "https://example.com/pic.jpg",
    }

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.google_oauth.exchange_code", new_callable=AsyncMock, return_value="tok"),
            patch("app.services.google_oauth.verify_id_token", new_callable=AsyncMock, return_value=google_info),
            patch("app.services.jwt_service.settings") as ms,
        ):
            ms.jwt_secret = _JWT_SECRET
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/auth/callback",
                    json={"code": "auth_code", "code_verifier": "verifier"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["is_new_user"] is True
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_callback_returning_user(db_session: AsyncSession) -> None:
    """POST /api/auth/callback for an existing user returns is_new_user=False."""
    from app.main import app

    user = await create_test_user(db_session)
    google_info: dict[str, Any] = {
        "sub": user.google_id,
        "email": user.email,
        "name": user.display_name,
        "picture": None,
    }

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.google_oauth.exchange_code", new_callable=AsyncMock, return_value="tok"),
            patch("app.services.google_oauth.verify_id_token", new_callable=AsyncMock, return_value=google_info),
            patch("app.services.jwt_service.settings") as ms,
        ):
            ms.jwt_secret = _JWT_SECRET
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/auth/callback",
                    json={"code": "code", "code_verifier": "verifier"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["is_new_user"] is False


@pytest.mark.asyncio
async def test_callback_google_failure_returns_401() -> None:
    """POST /api/auth/callback with a Google error returns 401."""
    from app.main import app

    with patch("app.services.google_oauth.exchange_code", side_effect=Exception("google down")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/callback",
                json={"code": "bad", "code_verifier": "v"},
            )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_callback_missing_body_returns_422() -> None:
    """POST /api/auth/callback without required fields returns 422."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/callback", json={})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_no_cookie_returns_401() -> None:
    """POST /api/auth/refresh without a cookie returns 401."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/refresh")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_valid_token_returns_new_access_cookie(db_session: AsyncSession) -> None:
    """POST /api/auth/refresh with a valid non-blacklisted token issues new cookie."""
    from app.main import app

    user = await create_test_user(db_session)
    refresh_tok = _make_jwt(user, timedelta(days=7))

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.jwt_service.settings") as ms:
            ms.jwt_secret = _JWT_SECRET
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"refresh_token": refresh_tok},
            ) as client:
                resp = await client.post("/api/auth/refresh")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_refresh_blacklisted_token_returns_401(db_session: AsyncSession) -> None:
    """POST /api/auth/refresh with a blacklisted jti returns 401."""
    from app.main import app

    user = await create_test_user(db_session)
    now = datetime.now(tz=timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": user.google_id,
        "user_id": str(user.id),
        "iat": now,
        "exp": now + timedelta(days=7),
        "jti": jti,
    }
    refresh_tok = pyjwt.encode(payload, _JWT_SECRET, algorithm="HS256")

    # Insert blacklist entry in test session
    entry = RefreshTokenBlacklist(jti=jti, user_id=user.id, expires_at=now + timedelta(days=7))
    db_session.add(entry)
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.jwt_service.settings") as ms:
            ms.jwt_secret = _JWT_SECRET
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"refresh_token": refresh_tok},
            ) as client:
                resp = await client.post("/api/auth/refresh")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_expired_token_returns_401() -> None:
    """POST /api/auth/refresh with an expired token returns 401."""
    from app.main import app

    # Build a token that is expired without needing a DB user
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": "g_test",
        "user_id": str(uuid.uuid4()),
        "iat": now - timedelta(days=8),
        "exp": now - timedelta(seconds=1),
        "jti": uuid.uuid4().hex,
    }
    expired_tok = pyjwt.encode(payload, _JWT_SECRET, algorithm="HS256")

    with patch("app.services.jwt_service.settings") as ms:
        ms.jwt_secret = _JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"refresh_token": expired_tok},
        ) as client:
            resp = await client.post("/api/auth/refresh")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_no_cookie_returns_200() -> None:
    """POST /api/auth/logout without a cookie still returns 200."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/auth/logout")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_logout_with_valid_token_returns_200_and_clears_cookies(db_session: AsyncSession) -> None:
    """POST /api/auth/logout with a valid token returns 200 and clears auth cookies."""
    from app.main import app

    user = await create_test_user(db_session)
    refresh_tok = _make_jwt(user, timedelta(days=7))

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch("app.services.jwt_service.settings") as ms:
            ms.jwt_secret = _JWT_SECRET
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={"refresh_token": refresh_tok, "access_token": "dummy"},
            ) as client:
                resp = await client.post("/api/auth/logout")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    # Cookies should be cleared (Set-Cookie with max-age=0 or empty value)
    set_cookie_headers = (
        resp.headers.get_list("set-cookie")
        if hasattr(resp.headers, "get_list")
        else [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
    )
    assert any("access_token" in h for h in set_cookie_headers)
    assert any("refresh_token" in h for h in set_cookie_headers)
