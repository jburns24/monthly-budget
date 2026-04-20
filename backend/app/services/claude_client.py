"""Claude API client for receipt data extraction.

Wraps the AsyncAnthropic SDK with tenacity retry logic layered on top of the
SDK's built-in retries (max_retries=2). Tenacity handles transient server errors
(5xx, 429) with exponential back-off; the SDK handles connection-level retries.
"""

import base64
from typing import Literal

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.logging import get_logger
from app.schemas.receipt import ExtractedReceipt

logger = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024
_SYSTEM_PROMPT = (
    "You are a receipt data extractor. Extract the total amount, date, and store name from the receipt image."
)
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
async def extract_receipt(
    client: AsyncAnthropic,
    image_bytes: bytes,
    media_type: MediaType = "image/jpeg",
) -> ExtractedReceipt:
    """Call Claude to extract structured data from a receipt image.

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
        On unretryable 4xx errors (e.g. 400 invalid request, 401 auth failure).
    ValueError
        If Claude returns no tool_use block in the response (unexpected schema).
    """
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
                    }
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
