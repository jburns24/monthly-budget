"""Pytest configuration and fixtures."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User

# ---------------------------------------------------------------------------
# JWT helpers (HS256, same algorithm as the production JWT service)
# ---------------------------------------------------------------------------

_JWT_ALGORITHM = "HS256"
# Use a guaranteed-length secret for tests when jwt_secret is not configured.
_raw_jwt_secret: str = getattr(settings, "jwt_secret", "")
_TEST_JWT_SECRET = _raw_jwt_secret if len(_raw_jwt_secret) >= 32 else "test-secret-key-for-tests-only-32char!!"

# ---------------------------------------------------------------------------
# Test database engine (shared across the session; each test rolls back)
# ---------------------------------------------------------------------------

_test_engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    """Configure async test backend."""
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test transaction rollback for isolation.

    Each test runs inside a transaction that is always rolled back at teardown,
    so no test data leaks into subsequent tests.

    Example::

        async def test_something(db_session):
            user = await create_test_user(db_session)
            result = await db_session.get(User, user.id)
            assert result is not None
    """
    session = AsyncSession(_test_engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


# ---------------------------------------------------------------------------
# User factory (plain async function, not a fixture — call it from any fixture
# or test that already has a db_session)
# ---------------------------------------------------------------------------


async def create_test_user(db: AsyncSession, **overrides: Any) -> User:
    """Insert a User into the test database and return the ORM object.

    Parameters
    ----------
    db:
        Active async session (typically from the :func:`db_session` fixture).
    **overrides:
        Field values that replace the auto-generated defaults.  Pass any
        combination of User column names.

    Returns
    -------
    User
        The persisted :class:`~app.models.user.User` instance.

    Example::

        user = await create_test_user(db_session, email="alice@example.com", display_name="Alice")
    """
    now = datetime.now(tz=timezone.utc)
    unique = uuid.uuid4().hex[:8]
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "google_id": f"google_{unique}",
        "email": f"test_{unique}@example.com",
        "display_name": "Test User",
        "avatar_url": None,
        "timezone": "America/New_York",
        "created_at": now,
        "last_login_at": now,
    }
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Internal JWT helpers
# ---------------------------------------------------------------------------


def _make_jwt(user: User, expires_in: timedelta) -> str:
    """Return a signed JWT for *user* that expires after *expires_in*."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.google_id,
        "user_id": str(user.id),
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm=_JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def authenticated_client() -> Any:
    """Factory fixture — call with a User to get an AsyncClient with JWT cookies.

    The returned callable accepts a :class:`~app.models.user.User` and returns a
    configured :class:`httpx.AsyncClient` with ``access_token`` (15-min) and
    ``refresh_token`` (7-day) HttpOnly-style cookies pre-set.

    Use the returned client as an async context manager::

        async def test_me(authenticated_client, db_session):
            user = await create_test_user(db_session)
            async with authenticated_client(user) as client:
                resp = await client.get("/api/me")
                assert resp.status_code == 200
    """
    from app.main import app

    def _make(user: User) -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={
                "access_token": _make_jwt(user, timedelta(minutes=15)),
                "refresh_token": _make_jwt(user, timedelta(days=7)),
            },
        )

    return _make


@pytest.fixture
def mock_google_oauth() -> Any:
    """Factory fixture — patch Google token verification with a configurable payload.

    Returns a callable that accepts a *user_info* dict and returns a
    :func:`unittest.mock.patch` context manager.  The patch replaces
    ``google.oauth2.id_token.verify_oauth2_token`` so tests do not require
    live Google network access::

        def test_callback(mock_google_oauth):
            user_info = {
                "sub": "google_abc123",
                "email": "alice@example.com",
                "name": "Alice",
                "picture": "https://example.com/alice.jpg",
            }
            with mock_google_oauth(user_info):
                # /api/auth/callback will receive user_info instead of contacting Google
                resp = await client.post(
                    "/api/auth/callback",
                    json={"code": "auth_code", "code_verifier": "verifier"},
                )
    """

    def _make(user_info: dict[str, Any]):
        return patch("google.oauth2.id_token.verify_oauth2_token", return_value=user_info)

    return _make
