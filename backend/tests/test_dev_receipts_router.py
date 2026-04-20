"""Tests for the dev-only mock-claude toggle endpoint.

Covers:
- POST /api/dev/mock-claude?scenario=... returns {"scenario": "..."} in dev
- Route updates settings.anthropic_mock_scenario in-process
- Route returns HTTP 404 in production (env gate check)
- Default scenario is "success" when no query param given
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTPX client wired to the FastAPI app (no DB needed)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_scenario_returns_scenario_json(client: AsyncClient) -> None:
    """POST /api/dev/mock-claude?scenario=non_receipt returns {"scenario": "non_receipt"}."""
    original = settings.anthropic_mock_scenario
    try:
        response = await client.post("/api/dev/mock-claude?scenario=non_receipt")
        assert response.status_code == 200
        assert response.json() == {"scenario": "non_receipt"}
    finally:
        settings.anthropic_mock_scenario = original


@pytest.mark.asyncio
async def test_set_scenario_updates_settings(client: AsyncClient) -> None:
    """Route mutates settings.anthropic_mock_scenario for the process."""
    original = settings.anthropic_mock_scenario
    try:
        await client.post("/api/dev/mock-claude?scenario=api_error")
        assert settings.anthropic_mock_scenario == "api_error"
    finally:
        settings.anthropic_mock_scenario = original


@pytest.mark.asyncio
async def test_default_scenario_is_success(client: AsyncClient) -> None:
    """When no scenario query param is given, defaults to 'success'."""
    original = settings.anthropic_mock_scenario
    try:
        response = await client.post("/api/dev/mock-claude")
        assert response.status_code == 200
        assert response.json() == {"scenario": "success"}
    finally:
        settings.anthropic_mock_scenario = original


@pytest.mark.asyncio
async def test_all_named_scenarios_accepted(client: AsyncClient) -> None:
    """All five documented scenarios are accepted."""
    scenarios = ["success", "medium_confidence", "low_confidence", "non_receipt", "api_error"]
    original = settings.anthropic_mock_scenario
    try:
        for scenario in scenarios:
            response = await client.post(f"/api/dev/mock-claude?scenario={scenario}")
            assert response.status_code == 200, f"Expected 200 for scenario={scenario!r}"
            assert response.json() == {"scenario": scenario}
    finally:
        settings.anthropic_mock_scenario = original


# ---------------------------------------------------------------------------
# Environment gate: must return 404 in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_route_returns_404_in_production() -> None:
    """Route raises HTTP 404 when environment is 'production'."""
    with patch.object(settings, "environment", "production"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/dev/mock-claude?scenario=success")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mock_route_returns_404_in_staging() -> None:
    """Route raises HTTP 404 when environment is 'staging'."""
    with patch.object(settings, "environment", "staging"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/dev/mock-claude?scenario=success")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mock_route_accessible_in_test_env() -> None:
    """Route is accessible (200) when environment is 'test'."""
    original = settings.anthropic_mock_scenario
    try:
        with patch.object(settings, "environment", "test"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/dev/mock-claude?scenario=success")
        assert response.status_code == 200
    finally:
        settings.anthropic_mock_scenario = original
