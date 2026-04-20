"""Tests for T02.3: Mock branch with 5 deterministic scenarios."""

from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIStatusError

from app.services.claude_client import extract_receipt


def _make_client() -> MagicMock:
    """Return a mock client that should NOT be called in mock mode."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = MagicMock(side_effect=AssertionError("Real API called during mock mode"))
    return client


@pytest.mark.asyncio
async def test_mock_success_scenario() -> None:
    """Mock 'success' returns high-confidence receipt with all fields."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "success"

        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    assert result.confidence == "high"
    assert result.total_amount == 42.50
    assert result.date == "2026-03-21"
    assert result.store_name == "Test Market"
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_mock_medium_confidence_scenario() -> None:
    """Mock 'medium_confidence' returns medium-confidence receipt with no date."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "medium_confidence"

        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    assert result.confidence == "medium"
    assert result.total_amount == 42.50
    assert result.date is None
    assert result.store_name == "Test Market"
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_mock_low_confidence_scenario() -> None:
    """Mock 'low_confidence' returns low-confidence receipt with no extracted fields."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "low_confidence"

        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    assert result.confidence == "low"
    assert result.total_amount is None
    assert result.date is None
    assert result.store_name is None
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_mock_non_receipt_scenario() -> None:
    """Mock 'non_receipt' returns is_receipt=False."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "non_receipt"

        result = await extract_receipt(client, b"image")

    assert result.is_receipt is False
    assert result.confidence == "high"
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_mock_api_error_scenario() -> None:
    """Mock 'api_error' raises APIStatusError without calling the real client."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "api_error"

        with pytest.raises(APIStatusError) as exc_info:
            await extract_receipt(client, b"image")

    assert exc_info.value.status_code == 503
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_mock_disabled_calls_real_client() -> None:
    """When anthropic_mock=False, extract_receipt calls the real client."""
    from unittest.mock import AsyncMock

    block = MagicMock()
    block.type = "tool_use"
    block.input = {"is_receipt": True, "confidence": "high"}
    usage = MagicMock()
    usage.input_tokens = 10
    usage.output_tokens = 5
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    response.usage = usage

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = False
        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_mock_unknown_scenario_falls_back_to_success() -> None:
    """Unknown mock scenario falls back to 'success' without error."""
    client = _make_client()
    with patch("app.services.claude_client.settings") as mock_settings:
        mock_settings.anthropic_mock = True
        mock_settings.anthropic_mock_scenario = "does_not_exist"

        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    assert result.confidence == "high"
    assert result.total_amount == 42.50
    client.messages.create.assert_not_called()
