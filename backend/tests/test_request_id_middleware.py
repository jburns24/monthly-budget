"""Tests for T06: RequestIDMiddleware."""

import re

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_request_id_echoed_on_response() -> None:
    """X-Request-ID sent in request is echoed back in the response header."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health", headers={"X-Request-ID": "test-req-id-abc"})
    assert response.headers.get("x-request-id") == "test-req-id-abc"


@pytest.mark.asyncio
async def test_request_id_generated_when_absent() -> None:
    """Middleware generates a UUID4 when no X-Request-ID header is provided."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    # UUID4 format: 8-4-4-4-12 hex chars
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    assert uuid_pattern.match(request_id), f"Expected UUID4, got: {request_id}"


@pytest.mark.asyncio
async def test_request_id_echoed_and_logged() -> None:
    """X-Request-ID round-trips and structlog events in the same request include it."""
    log_events: list[dict] = []

    def capture_processor(logger, method, event_dict):  # type: ignore[no-untyped-def]
        log_events.append(dict(event_dict))
        return event_dict

    # Temporarily insert a capturing processor before the first processor
    original_processors = structlog.get_config()["processors"]
    structlog.configure(processors=[capture_processor, *original_processors])

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    finally:
        structlog.configure(processors=original_processors)

    assert response.headers.get("x-request-id") == "trace-abc-123"


@pytest.mark.asyncio
async def test_different_requests_get_different_ids() -> None:
    """Two requests without X-Request-ID get distinct generated IDs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/api/health")
        r2 = await client.get("/api/health")
    id1 = r1.headers.get("x-request-id")
    id2 = r2.headers.get("x-request-id")
    assert id1 != id2


@pytest.mark.asyncio
async def test_sensitive_filter_redacts_keys() -> None:
    """SensitiveFilter redacts known sensitive keys in event dicts."""
    from app.logging import _sensitive_filter

    event_dict = {
        "event": "startup",
        "anthropic_api_key": "sk-ant-real-key",  # pragma: allowlist secret
        "jwt_secret": "super-secret",  # pragma: allowlist secret
        "password": "hunter2",  # pragma: allowlist secret
        "authorization": "Bearer token123",  # pragma: allowlist secret
        "google_client_secret": "google-secret",  # pragma: allowlist secret
        "safe_key": "safe_value",
    }
    result = _sensitive_filter(None, "info", event_dict)
    assert result["anthropic_api_key"] == "[REDACTED]"
    assert result["jwt_secret"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["google_client_secret"] == "[REDACTED]"
    assert result["safe_key"] == "safe_value"
    assert result["event"] == "startup"
