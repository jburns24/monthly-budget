"""Placeholder tests verifying the app can be imported and basic health response shape."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def test_app_importable() -> None:
    """Verify the FastAPI app object can be imported without errors."""
    from app.main import app  # noqa: F401

    assert app is not None
    assert app.title == "Monthly Budget API"


@pytest.mark.asyncio
async def test_health_endpoint_schema() -> None:
    """Verify /api/health returns a dict with expected keys.

    Database and Redis checks are mocked so the test does not require
    live infrastructure.
    """
    from app.main import app

    with (
        patch(
            "app.routers.health._check_database",
            new_callable=AsyncMock,
            return_value=(True, "connected"),
        ),
        patch(
            "app.routers.health._check_redis",
            new_callable=AsyncMock,
            return_value=(True, "connected"),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "database" in body
    assert "redis" in body
    assert body["status"] == "healthy"
