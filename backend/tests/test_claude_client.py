"""Tests for T02.2: extract_receipt function — request builder, parser, tenacity retry."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from anthropic import APIConnectionError, APIStatusError

from app.schemas.receipt import ExtractedReceipt
from app.services.claude_client import _MODEL, CATEGORY_LABELS, extract_receipt

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
        "total": 47.23,
        "date": "2026-03-21",
        "name": "Whole Foods Market",
        "category": "Groceries",
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
    assert result.category == "Groceries"


@pytest.mark.asyncio
async def test_extract_receipt_maps_wire_aliases_to_field_names() -> None:
    """The wire keys name/total map onto .store_name/.total_amount, and only those.

    Guards the alias contract both ways: the pipeline reads the long attribute
    names, while Receipt.raw_response must keep serializing under them too.
    """
    tool_input = {"is_receipt": True, "confidence": "high", "name": "Safeway", "total": 12.5}
    client = _make_client(_make_tool_use_response(tool_input))

    result = await extract_receipt(client, b"fake-image-bytes")

    assert result.store_name == "Safeway"
    assert result.total_amount == 12.5
    dumped = result.model_dump()
    assert dumped["store_name"] == "Safeway"
    assert dumped["total_amount"] == 12.5
    assert "name" not in dumped
    assert "total" not in dumped


@pytest.mark.asyncio
async def test_extract_receipt_coerces_stringified_null_to_none() -> None:
    """A literal "null" string for an unreadable field becomes None, not an error.

    Regression, caught against the live API: asked for a receipt whose total was
    cropped out of frame, Haiku returned {"total": "null"} — a string, because the
    schema typed total as a number and gave it no legal way to say "unreadable".
    That failed float parsing and turned the upload into a 503. The date case is
    quieter and worse: "null" validates as a str, then _parse_expense_date falls
    back to today, silently dating the expense wrong.
    """
    tool_input = {
        "is_receipt": True,
        "confidence": "low",
        "total": "null",
        "date": "null",
        "name": "N/A",
        "category": "",
    }
    client = _make_client(_make_tool_use_response(tool_input))

    result = await extract_receipt(client, b"cropped-image")

    assert result.total_amount is None
    assert result.date is None
    assert result.store_name is None
    assert result.category is None


@pytest.mark.asyncio
async def test_extract_receipt_accepts_real_json_null() -> None:
    """Explicit JSON nulls validate too — the schema now permits them."""
    tool_input = {
        "is_receipt": True,
        "confidence": "low",
        "total": None,
        "date": None,
        "name": None,
        "category": None,
    }
    client = _make_client(_make_tool_use_response(tool_input))

    result = await extract_receipt(client, b"blurry-image")

    assert result.total_amount is None
    assert result.date is None
    assert result.store_name is None


@pytest.mark.asyncio
async def test_extract_receipt_optional_fields_permit_null_in_schema() -> None:
    """Optional fields advertise a null-able type so "unreadable" is expressible."""
    client = _make_client(_make_tool_use_response({"is_receipt": True, "confidence": "high"}))

    await extract_receipt(client, b"fake-image-bytes")

    props = client.messages.create.call_args.kwargs["tools"][0]["input_schema"]["properties"]
    for field in ("total", "date", "name", "category"):
        assert "null" in props[field]["type"], f"{field} cannot express 'unreadable'"


@pytest.mark.asyncio
async def test_extract_receipt_tool_schema_uses_wire_names_and_category_enum() -> None:
    """The tool schema advertises name/total/category, with category constrained."""
    client = _make_client(_make_tool_use_response({"is_receipt": True, "confidence": "high"}))

    await extract_receipt(client, b"fake-image-bytes")

    props = client.messages.create.call_args.kwargs["tools"][0]["input_schema"]["properties"]
    assert set(props) == {
        "date_reasoning",
        "is_receipt",
        "confidence",
        "total",
        "date",
        "name",
        "category",
    }
    # None is a permitted enum member so a non-receipt can leave the field unset
    # without violating the schema it was handed.
    assert props["category"]["enum"] == [*CATEGORY_LABELS, None]


@pytest.mark.asyncio
async def test_extract_receipt_system_prompt_is_phased() -> None:
    """The system prompt walks the model through all six extraction phases."""
    client = _make_client(_make_tool_use_response({"is_receipt": True, "confidence": "high"}))

    await extract_receipt(client, b"fake-image-bytes")

    system = client.messages.create.call_args.kwargs["system"]
    for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6"):
        assert phase in system
    # Every category the schema allows must also be described in the prompt,
    # or the model is choosing from a list it was never shown.
    for label in CATEGORY_LABELS:
        assert label in system


@pytest.mark.asyncio
async def test_extract_receipt_tells_the_model_todays_date() -> None:
    """The request must carry the current date.

    Regression guard. The model has no clock, so with no reference date in the
    prompt an absent or illegible year on the receipt is resolved against the
    year distribution of its training data — which lands the expense in a
    previous year, on a month the UI is not showing, with nothing downstream
    able to detect it. Asserted on the outgoing request rather than on the
    prompt constant so that building the prompt without wiring it into the call
    also fails.
    """
    from datetime import date

    client = _make_client(_make_tool_use_response({"is_receipt": True, "confidence": "high"}))

    await extract_receipt(client, b"fake-image-bytes")

    system = client.messages.create.call_args.kwargs["system"]
    assert date.today().isoformat() in system


def test_system_prompt_date_is_not_frozen_at_import() -> None:
    """The date is rendered per call, not baked in when the module loads.

    A module-level f-string would pin the date to the worker's start-up day and
    drift further wrong for as long as the process lives.
    """
    from datetime import date

    from app.services.claude_client import _build_system_prompt

    assert "2030-01-02" in _build_system_prompt(date(2030, 1, 2))
    assert "2031-06-15" in _build_system_prompt(date(2031, 6, 15))


def test_system_prompt_biases_years_toward_today() -> None:
    """Phase 3 must prefer a date close to today when the year is ambiguous.

    Prod keeps filing this year's purchases under last year: the model has no
    clock and a printed-looking year from training data wins over recency.
    The prompt has to say the receipt is likely from this month and that a
    year landing far in the past is a misread to re-check, not a fact to trust.
    """
    from datetime import date

    from app.services.claude_client import _build_system_prompt

    system = _build_system_prompt(date(2026, 7, 26))
    assert "likely from this month" in system
    assert "most recent year" in system
    assert "cannot have happened in the future" in system
    assert "re-read the year" in system


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
async def test_extract_receipt_builds_correct_request() -> None:
    """extract_receipt builds the exact PRD §13 request shape.

    User message content must be a list of exactly [image_block, text_block]:
      - image_block: {"type": "image", "source": {"type": "base64", "media_type": ..., "data": <b64>}}
      - text_block:  {"type": "text", "text": "Extract structured data from this receipt image."}
    """
    import base64
    from datetime import date

    from app.services.claude_client import _MAX_TOKENS, _USER_TEXT_PROMPT, _build_system_prompt

    image_bytes = b"prd-section-13-bytes"
    expected_b64 = base64.standard_b64encode(image_bytes).decode()

    tool_input = {"is_receipt": True, "confidence": "high"}
    response = _make_tool_use_response(tool_input)
    client = _make_client(response)

    await extract_receipt(client, image_bytes, media_type="image/jpeg")

    call_kwargs = client.messages.create.call_args.kwargs

    assert call_kwargs["model"] == _MODEL
    assert call_kwargs["max_tokens"] == _MAX_TOKENS
    assert call_kwargs["system"] == _build_system_prompt(date.today())
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "extract_receipt"}

    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"

    content = messages[0]["content"]
    assert isinstance(content, list)
    assert len(content) == 2, f"Expected [image_block, text_block]; got {content!r}"

    image_block, text_block = content
    assert image_block == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": expected_b64,
        },
    }
    assert text_block == {"type": "text", "text": _USER_TEXT_PROMPT}
    assert text_block["text"] == "Extract structured data from this receipt image."


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
