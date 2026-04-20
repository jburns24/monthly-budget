"""Claude API client for receipt data extraction.

Wraps the AsyncAnthropic SDK with tenacity retry logic layered on top of the
SDK's built-in retries (max_retries=2). Tenacity handles transient server errors
(5xx, 429) with exponential back-off; the SDK handles connection-level retries.

When settings.anthropic_mock is True, extract_receipt returns a deterministic
ExtractedReceipt based on settings.anthropic_mock_scenario without calling the API.
"""

import base64
from typing import Literal

import httpx
from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings
from app.logging import get_logger
from app.schemas.receipt import ExtractedReceipt

logger = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024
_SYSTEM_PROMPT = (
    "You are a receipt data extractor. Extract the total amount, date, and store name from the receipt image."
)
_USER_TEXT_PROMPT = "Extract structured data from this receipt image."
_TOOL_DEFINITION = {
    "name": "extract_receipt",
    "description": "Extract structured data from a receipt image",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_receipt": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "total_amount": {"type": "number"},
            "date": {"type": "string", "description": "YYYY-MM-DD or null"},
            "store_name": {"type": "string", "description": "Merchant name or null"},
        },
        "required": ["is_receipt", "confidence"],
    },
}

MediaType = Literal["image/jpeg", "image/png", "image/webp", "image/gif"]

_MOCK_SCENARIOS: dict[str, ExtractedReceipt] = {
    "success": ExtractedReceipt(
        is_receipt=True,
        confidence="high",
        total_amount=42.50,
        date="2026-03-21",
        store_name="Test Market",
    ),
    "medium_confidence": ExtractedReceipt(
        is_receipt=True,
        confidence="medium",
        total_amount=42.50,
        date=None,
        store_name="Test Market",
    ),
    "low_confidence": ExtractedReceipt(
        is_receipt=True,
        confidence="low",
        total_amount=None,
        date=None,
        store_name=None,
    ),
    "non_receipt": ExtractedReceipt(
        is_receipt=False,
        confidence="high",
    ),
}

_MOCK_API_ERROR_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _get_mock_response(scenario: str) -> ExtractedReceipt:
    """Return a deterministic ExtractedReceipt for the given mock scenario.

    Raises APIStatusError for the 'api_error' scenario.
    Falls back to 'success' for unknown scenario names.
    """
    if scenario == "api_error":
        raise APIStatusError(
            "Mock Anthropic API error (scenario: api_error)",
            response=httpx.Response(503, request=_MOCK_API_ERROR_REQUEST),
            body=None,
        )
    result = _MOCK_SCENARIOS.get(scenario)
    if result is None:
        logger.warning("claude_mock_unknown_scenario", scenario=scenario, fallback="success")
        result = _MOCK_SCENARIOS["success"]
    return result


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504):
        return True
    return False


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)


@_retry
async def _call_claude(
    client: AsyncAnthropic,
    image_bytes: bytes,
    media_type: MediaType,
) -> ExtractedReceipt:
    """Send an image to Claude and parse the tool-use response. Wrapped by tenacity."""
    b64_data = base64.standard_b64encode(image_bytes).decode()

    logger.info("claude_extract_receipt_start", image_size=len(image_bytes), media_type=media_type)

    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "extract_receipt"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {"type": "text", "text": _USER_TEXT_PROMPT},
                ],
            }
        ],
    )

    tool_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise ValueError(f"Claude returned no tool_use block; stop_reason={response.stop_reason!r}")

    extracted = ExtractedReceipt.model_validate(tool_block.input)

    logger.info(
        "claude_extract_receipt_complete",
        is_receipt=extracted.is_receipt,
        confidence=extracted.confidence,
        has_total=extracted.total_amount is not None,
        has_date=extracted.date is not None,
        has_store=extracted.store_name is not None,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    return extracted


async def extract_receipt(
    client: AsyncAnthropic,
    image_bytes: bytes,
    media_type: MediaType = "image/jpeg",
) -> ExtractedReceipt:
    """Call Claude to extract structured data from a receipt image.

    When settings.anthropic_mock is True, returns a deterministic response
    for the scenario in settings.anthropic_mock_scenario without calling the API.

    Parameters
    ----------
    client:
        The AsyncAnthropic singleton from app.state.
    image_bytes:
        Raw image bytes (already sanitized/re-encoded by receipt_storage).
    media_type:
        MIME type of the image (default: image/jpeg after sanitization).

    Returns
    -------
    ExtractedReceipt
        Parsed tool-use response from Claude.

    Raises
    ------
    APIStatusError
        On unretryable 4xx errors or when mock scenario is 'api_error'.
    ValueError
        If Claude returns no tool_use block in the response (unexpected schema).
    """
    if settings.anthropic_mock:
        scenario = settings.anthropic_mock_scenario
        logger.info("claude_extract_receipt_mock", scenario=scenario)
        return _get_mock_response(scenario)

    return await _call_claude(client, image_bytes, media_type)
