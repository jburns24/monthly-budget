"""Tests for T02.2: extract_receipt function — request builder, parser, tenacity retry."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from anthropic import APIConnectionError, APIStatusError

from app.schemas.receipt import ExtractedReceipt
from app.services.claude_client import _MODEL, extract_receipt

_ANTHROPIC_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _make_tool_use_response(tool_input: dict) -> MagicMock:
    """Build a mock AsyncAnthropic messages.create response with a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input

    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    response.usage = usage
    return response


def _make_client(response: MagicMock) -> AsyncMock:
    """Return a mock AsyncAnthropic client whose messages.create returns response."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_extract_receipt_success_full_fields() -> None:
    """extract_receipt returns ExtractedReceipt with all fields on happy path."""
    tool_input = {
        "is_receipt": True,
        "confidence": "high",
        "total_amount": 47.23,
        "date": "2026-03-21",
        "store_name": "Whole Foods Market",
    }
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    result = await extract_receipt(client, b"fake-image-bytes")

    assert isinstance(result, ExtractedReceipt)
    assert result.is_receipt is True
    assert result.confidence == "high"
    assert result.total_amount == 47.23
    assert result.date == "2026-03-21"
    assert result.store_name == "Whole Foods Market"


@pytest.mark.asyncio
async def test_extract_receipt_uses_correct_model_and_tool() -> None:
    """extract_receipt sends the expected model, tool name, and tool_choice."""
    tool_input = {"is_receipt": True, "confidence": "high"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    await extract_receipt(client, b"fake-image-bytes")

    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == _MODEL
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "extract_receipt"}
    tools = call_kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "extract_receipt"
    assert "is_receipt" in tools[0]["input_schema"]["properties"]
    assert "confidence" in tools[0]["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_extract_receipt_sends_base64_image() -> None:
    """extract_receipt encodes image bytes as base64 in the messages content."""
    import base64

    image_bytes = b"fake-receipt-image"
    expected_b64 = base64.standard_b64encode(image_bytes).decode()

    tool_input = {"is_receipt": True, "confidence": "medium"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    await extract_receipt(client, image_bytes, media_type="image/png")

    call_kwargs = client.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    image_block = next(b for b in content if b.get("type") == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["data"] == expected_b64


@pytest.mark.asyncio
async def test_extract_receipt_partial_fields() -> None:
    """extract_receipt returns ExtractedReceipt with optional fields as None."""
    tool_input = {"is_receipt": True, "confidence": "low"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    result = await extract_receipt(client, b"blurry-image")

    assert result.is_receipt is True
    assert result.confidence == "low"
    assert result.total_amount is None
    assert result.date is None
    assert result.store_name is None


@pytest.mark.asyncio
async def test_extract_receipt_non_receipt_image() -> None:
    """extract_receipt returns is_receipt=False for non-receipt images."""
    tool_input = {"is_receipt": False, "confidence": "high"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    result = await extract_receipt(client, b"selfie-bytes")

    assert result.is_receipt is False
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_extract_receipt_raises_value_error_on_no_tool_block() -> None:
    """extract_receipt raises ValueError if Claude returns no tool_use block."""
    text_block = MagicMock()
    text_block.type = "text"

    usage = MagicMock()
    usage.input_tokens = 50
    usage.output_tokens = 10

    response = MagicMock()
    response.content = [text_block]
    response.stop_reason = "end_turn"
    response.usage = usage

    client = _make_client(response)

    with pytest.raises(ValueError, match="no tool_use block"):
        await extract_receipt(client, b"weird-response")


@pytest.mark.asyncio
async def test_extract_receipt_retries_on_500() -> None:
    """extract_receipt retries up to 3 times on APIStatusError 500."""
    good_response = _make_tool_use_response({"is_receipt": True, "confidence": "high"})

    httpx_response = httpx.Response(500, request=_ANTHROPIC_REQUEST)
    error = APIStatusError("server error", response=httpx_response, body=None)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[error, error, good_response])

    with patch("asyncio.sleep"):
        result = await extract_receipt(client, b"image")

    assert result.is_receipt is True
    assert client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_extract_receipt_retries_on_429() -> None:
    """extract_receipt retries on rate-limit (429) errors."""
    good_response = _make_tool_use_response({"is_receipt": True, "confidence": "medium"})

    httpx_response = httpx.Response(429, request=_ANTHROPIC_REQUEST)
    error = APIStatusError("rate limited", response=httpx_response, body=None)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[error, good_response])

    with patch("asyncio.sleep"):
        result = await extract_receipt(client, b"image")

    assert client.messages.create.call_count == 2
    assert result.confidence == "medium"


@pytest.mark.asyncio
async def test_extract_receipt_raises_after_max_retries() -> None:
    """extract_receipt raises APIStatusError after exhausting 3 attempts."""
    httpx_response = httpx.Response(503, request=_ANTHROPIC_REQUEST)
    error = APIStatusError("unavailable", response=httpx_response, body=None)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=error)

    with patch("asyncio.sleep"):
        with pytest.raises(APIStatusError):
            await extract_receipt(client, b"image")

    assert client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_extract_receipt_retries_on_connection_error() -> None:
    """extract_receipt retries on APIConnectionError."""
    good_response = _make_tool_use_response({"is_receipt": True, "confidence": "high"})
    conn_error = APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[conn_error, good_response])

    with patch("asyncio.sleep"):
        result = await extract_receipt(client, b"image")

    assert client.messages.create.call_count == 2
    assert result.is_receipt is True


@pytest.mark.asyncio
async def test_extract_receipt_does_not_retry_on_400() -> None:
    """extract_receipt does NOT retry on 400 bad request (client error)."""
    httpx_response = httpx.Response(400, request=_ANTHROPIC_REQUEST)
    error = APIStatusError("bad request", response=httpx_response, body=None)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=error)

    with pytest.raises(APIStatusError):
        await extract_receipt(client, b"image")

    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_extract_receipt_default_media_type_is_jpeg() -> None:
    """extract_receipt defaults to image/jpeg media_type."""
    tool_input = {"is_receipt": True, "confidence": "high"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    await extract_receipt(client, b"jpeg-bytes")

    call_kwargs = client.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    image_block = next(b for b in messages[0]["content"] if b.get("type") == "image")
    assert image_block["source"]["media_type"] == "image/jpeg"
