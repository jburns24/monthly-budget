"""Full-flow backend integration test.

Exercises the complete auth lifecycle in a single test:
  OAuth callback (mocked Google) → GET /api/me → POST /api/auth/refresh
  → POST /api/auth/logout → GET /api/me returns 401
  → refresh token jti is blacklisted in the DB
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.refresh_token_blacklist import RefreshTokenBlacklist
from tests.conftest import _TEST_JWT_SECRET

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


def override_get_db(session: AsyncSession):
    """Return a FastAPI dependency override that yields *session*."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# Full-flow integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_auth_flow(db_session: AsyncSession) -> None:
    """Full auth lifecycle: callback → /api/me → refresh → logout → 401 → blacklist check."""
    from app.main import app

    google_sub = f"google_{uuid.uuid4().hex[:8]}"
    google_email = f"integration_{uuid.uuid4().hex[:6]}@example.com"
    google_info: dict[str, Any] = {
        "sub": google_sub,
        "email": google_email,
        "name": "Integration User",
        "picture": "https://example.com/pic.jpg",
    }

    captured_refresh_jti: str | None = None

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.google_oauth.exchange_code", new_callable=AsyncMock, return_value="id_tok"),
            patch("app.services.google_oauth.verify_id_token", new_callable=AsyncMock, return_value=google_info),
            patch("app.services.jwt_service.settings") as ms,
        ):
            ms.jwt_secret = _TEST_JWT_SECRET

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # ── Step 1: OAuth callback ──────────────────────────────────
                resp1 = await client.post(
                    "/api/auth/callback",
                    json={"code": "auth_code", "code_verifier": "verifier"},
                )
                assert resp1.status_code == 200, f"callback failed: {resp1.text}"
                assert resp1.json()["is_new_user"] is True
                assert "access_token" in client.cookies, "access_token cookie not set after callback"
                assert "refresh_token" in client.cookies, "refresh_token cookie not set after callback"

                # Capture refresh token jti before it may be cleared
                refresh_tok_raw = client.cookies.get("refresh_token")
                if refresh_tok_raw:
                    try:
                        payload = pyjwt.decode(refresh_tok_raw, _TEST_JWT_SECRET, algorithms=["HS256"])
                        captured_refresh_jti = payload.get("jti")
                    except pyjwt.InvalidTokenError:
                        pass

                # ── Step 2: GET /api/me ─────────────────────────────────────
                resp2 = await client.get("/api/me")
                assert resp2.status_code == 200, f"/api/me failed after callback: {resp2.text}"
                body2 = resp2.json()
                assert body2["email"] == google_email
                assert body2["display_name"] == "Integration User"
                assert "id" in body2

                # ── Step 3: POST /api/auth/refresh ──────────────────────────
                resp3 = await client.post("/api/auth/refresh")
                assert resp3.status_code == 200, f"refresh failed: {resp3.text}"
                assert "access_token" in client.cookies, "access_token not refreshed"

                # ── Step 4: POST /api/auth/logout ───────────────────────────
                resp4 = await client.post("/api/auth/logout")
                assert resp4.status_code == 200, f"logout failed: {resp4.text}"

                # Verify Set-Cookie headers clear both tokens
                set_cookie_headers = [v for k, v in resp4.headers.items() if k.lower() == "set-cookie"]
                assert any("access_token" in h for h in set_cookie_headers), "access_token not cleared on logout"
                assert any("refresh_token" in h for h in set_cookie_headers), "refresh_token not cleared on logout"

                # ── Step 5: GET /api/me → 401 ───────────────────────────────
                # Explicitly drop any lingering cookies so the request is unauthenticated
                client.cookies.clear()
                resp5 = await client.get("/api/me")
                assert resp5.status_code == 401, f"expected 401 after logout, got {resp5.status_code}: {resp5.text}"

    finally:
        app.dependency_overrides.pop(get_db, None)

    # ── Step 6: Verify refresh token jti is blacklisted in the DB ──────────
    assert captured_refresh_jti is not None, "Could not extract jti from refresh token"
    result = await db_session.execute(
        select(RefreshTokenBlacklist).where(RefreshTokenBlacklist.jti == captured_refresh_jti)
    )
    blacklist_entry = result.scalar_one_or_none()
    assert blacklist_entry is not None, f"Refresh token jti={captured_refresh_jti} not found in blacklist after logout"
