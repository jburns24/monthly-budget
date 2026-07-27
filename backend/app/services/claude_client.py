"""Claude API client for receipt data extraction.

Wraps the AsyncAnthropic SDK with tenacity retry logic layered on top of the
SDK's built-in retries (max_retries=2). Tenacity handles transient server errors
(5xx, 429) with exponential back-off; the SDK handles connection-level retries.

When settings.anthropic_mock is True, extract_receipt returns a deterministic
ExtractedReceipt based on settings.anthropic_mock_scenario without calling the API.
"""

import base64
from collections.abc import Callable
from datetime import date
from typing import Literal

import httpx
from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from anthropic.types import Usage
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings
from app.logging import get_logger
from app.schemas.receipt import ExtractedReceipt

logger = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
# Headroom for the date_reasoning field below. The extracted JSON itself is
# small, but truncating the tool input mid-object surfaces as a confusing
# model_validate failure rather than an obvious cap-hit, so leave slack.
_MAX_TOKENS = 2048

# Pinned rather than left to the API default of 1.0. Tuning against a real
# split-tender receipt showed this model's "which figure is the total" judgment
# is marginal under sampling: correct on every run at 0.0, but at 0.5 it reports
# the largest tender line instead of the amount charged - a confident wrong
# number, which is the worst failure mode here because nothing downstream can
# detect it. Only Haiku accepts this; Sonnet 5 rejects a non-default temperature
# under a forced tool_choice and Opus 5 rejects the parameter outright, so
# passing temperature=None omits the key entirely for those models.
DEFAULT_TEMPERATURE = 0.0

# Must stay in lockstep with category_service._DEFAULT_CATEGORIES: the label the
# model picks is fed to category_suggestion as a pg_trgm probe against the
# family's own category names, and families start from exactly these six.
CATEGORY_LABELS = ["Groceries", "Dining", "Transport", "Entertainment", "Bills", "Other"]

_CATEGORY_GUIDE = """\
  Groceries - supermarkets, food markets, butchers, produce
  Dining - restaurants, cafes, bars, coffee shops, takeout, delivery
  Transport - fuel, parking, tolls, transit, rideshare, vehicle service
  Entertainment - streaming, cinema, games, events, hobbies, books
  Bills - utilities, phone, internet, insurance, rent, subscriptions, medical
  Other - anything that does not clearly fit above, including general merchandise and clothing"""


def _build_system_prompt(today: date) -> str:
    """Render the extraction prompt for a given "today".

    Built per call rather than assembled once at import: the model has no clock,
    so Phase 3 has to be told the current date, and a module-level f-string would
    freeze that date for the lifetime of the worker process — a long-running
    uvicorn worker would keep telling the model it is still its start-up day.
    """
    return f"""\
You are a receipt data extractor. Work through the phases below in order, then report \
your result by calling the extract_receipt tool exactly once.

Phase 1 - Verify.
Decide whether the image shows a purchase receipt or invoice. Crumpled, faded, \
photographed at an angle, and partially cropped receipts all count. Menus, price tags, \
product photos, shipping labels, and unrelated documents do not. If it is not a receipt, \
set is_receipt to false and omit every other field - do not guess values off a \
non-receipt.

Phase 2 - Total.
Find the total charged for the purchase as a whole, not the customer's out-of-pocket \
share. Prefer the line labelled TOTAL, AMOUNT DUE, or BALANCE DUE: the figure after tax, \
after discounts, and after any tip. Payment and tender lines are not the total; when a \
purchase is settled across more than one tender, card, or account, each such line is only \
a share of it. Only when no total-style line is printed at all may you fall back to a \
payment line, and then only if a single payment settles the whole purchase. Never report \
SUBTOTAL, TAX, CHANGE DUE, a per-item price, or a loyalty or points balance. Report a \
bare positive number with no currency symbol and no thousands \
separator, for example 47.23. For a refund or return, report the absolute value.
Only ever report a total you can actually read on the receipt. Never derive one: do not \
add up the line items, do not add tax to a subtotal, and do not estimate. If the total \
line is missing, cut off, or illegible, omit the total field entirely - a receipt with no \
readable total is a normal outcome, and a computed figure would be wrong in a way nobody \
downstream can detect.

Phase 3 - Date.
Today's date is {today.isoformat()}. Use it only to work out which year a receipt belongs \
to and to sanity-check what you read; never report it as the transaction date.
Find the transaction date - the date of purchase, not a "valid until", "printed on", or \
expiry date. Normalize it to YYYY-MM-DD. To disambiguate a numeric format: a leading \
value above 12 is the day; otherwise, if the receipt shows US cues (dollar amounts, a US \
address, a state abbreviation) read it as MM/DD/YYYY, and read it as DD/MM/YYYY \
otherwise.
Resolve the year in this order:
  - A legible four-digit year is reported exactly as printed, even if it is years in the \
past. Never adjust a printed year toward today.
  - Expand a legible two-digit year to 20YY: 24 is 2024, 26 is 2026.
  - If the year is not printed at all, or is illegible, choose the most recent year that \
places the month and day on or before today's date. Do not default to the year you would \
otherwise assume - a receipt is almost always recent, and reporting last year's date for \
this year's purchase files the expense into a month nobody is looking at.
A purchase cannot have happened in the future. If your reading lands after today's date, \
you have misread something - re-read the field, and if you still cannot resolve it, omit \
the date field.
If no date is legible, omit the date field entirely - do not substitute today's date.

Phase 4 - Store name.
Report the merchant's brand name the way a person would say it, taken from the header, \
logo, or footer. Strip store numbers, legal suffixes, addresses, phone numbers, and \
register or lane identifiers: "WM SUPERCENTER #1234" becomes "Walmart", "SAFEWAY STORE \
0421" becomes "Safeway", "TRADER JOE'S #453" becomes "Trader Joe's". If the merchant is \
not identifiable, omit the name field entirely.

Phase 5 - Category.
Choose exactly one label based on what was actually bought, not on the store's official \
industry - an all-food run at a big-box store is Groceries, an all-clothing one is Other. \
Use the itemized lines to decide when the store is mixed-use.
{_CATEGORY_GUIDE}
For a genuine receipt you cannot classify, use "Other" rather than omitting the field.

Phase 6 - Confidence.
Report one overall confidence, anchored on the total:
  high - the image is clearly legible and you read the total and date directly off it
  medium - you read most fields but at least one required inference or was partly obscured
  low - the image is blurry, cropped, or dark enough that you are unsure of the total
Confidence is never high unless you read the total straight off a total line. If you \
omitted the total, confidence is low.

Never invent a value to fill a field, and never write the text "null" as a value. Leaving a \
field out is always the correct way to report something you cannot read."""


_USER_TEXT_PROMPT = "Extract structured data from this receipt image."
_TOOL_DEFINITION = {
    "name": "extract_receipt",
    "description": "Extract structured data from a receipt image",
    "input_schema": {
        "type": "object",
        "properties": {
            # First on purpose. Tool input is generated in schema order, and the
            # forced tool_choice means the model cannot emit a text block before
            # the tool call — so without a field to think in, Phase 3's year
            # resolution has to happen in one forward pass with no intermediate
            # tokens. This buys that room, and it is what gets logged when a date
            # still comes back wrong.
            "date_reasoning": {
                "type": ["string", "null"],
                "description": (
                    "One sentence: which field you read the date from, and how you "
                    "resolved its year against today's date"
                ),
            },
            "is_receipt": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            # Each optional field is typed as a union with "null" rather than a
            # bare scalar. With "type": "number" the model has no legal way to
            # say "unreadable" and emits the *string* "null", which fails
            # validation and 503s the upload.
            "total": {
                "type": ["number", "null"],
                "description": "Final amount paid; omit if not legible",
            },
            "date": {
                "type": ["string", "null"],
                "description": "Transaction date as YYYY-MM-DD; omit if not legible",
            },
            "name": {
                "type": ["string", "null"],
                "description": "Merchant brand name; omit if not identifiable",
            },
            "category": {
                "type": ["string", "null"],
                "enum": [*CATEGORY_LABELS, None],
                "description": "Spending category for the purchase; omit if not a receipt",
            },
        },
        "required": ["is_receipt", "confidence"],
    },
}

MediaType = Literal["image/jpeg", "image/png", "image/webp", "image/gif"]


def _mock_scenarios() -> dict[str, ExtractedReceipt]:
    """Build the deterministic mock scenarios, dated relative to today.

    The ``success`` date is computed per call rather than frozen at import time:
    a hardcoded date silently rots, and once it falls outside the current month
    the resulting Expense lands in a month the UI is not displaying, which reads
    as "the upload did nothing".
    """
    return {
        "success": ExtractedReceipt(
            is_receipt=True,
            confidence="high",
            total_amount=42.50,
            date=date.today().isoformat(),
            store_name="Test Market",
            category="Groceries",
        ),
        "medium_confidence": ExtractedReceipt(
            is_receipt=True,
            confidence="medium",
            total_amount=42.50,
            date=None,
            store_name="Test Market",
            category="Groceries",
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
    scenarios = _mock_scenarios()
    result = scenarios.get(scenario)
    if result is None:
        logger.warning("claude_mock_unknown_scenario", scenario=scenario, fallback="success")
        result = scenarios["success"]
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
    *,
    model: str | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    usage_callback: Callable[[Usage], None] | None = None,
) -> ExtractedReceipt:
    """Send an image to Claude and parse the tool-use response. Wrapped by tenacity.

    ``model``/``usage_callback`` are probe-only overrides (see
    test-scripts/scan_receipt_probe.py); left as None the pinned default model
    is used. ``temperature`` defaults to DEFAULT_TEMPERATURE; pass None to omit
    the key entirely, which is required for models that reject the parameter.
    """
    b64_data = base64.standard_b64encode(image_bytes).decode()

    logger.info("claude_extract_receipt_start", image_size=len(image_bytes), media_type=media_type)

    create_kwargs: dict = {}
    if temperature is not None:
        create_kwargs["temperature"] = temperature

    response = await client.messages.create(
        model=model or _MODEL,
        max_tokens=_MAX_TOKENS,
        system=_build_system_prompt(date.today()),
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
        **create_kwargs,
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
        category=extracted.category,
        # Not persisted on the Receipt — it is scaffolding for the model, not
        # data — but it is the only way to tell a misread year from a mis-picked
        # one when a date comes back wrong.
        date_reasoning=tool_block.input.get("date_reasoning") if isinstance(tool_block.input, dict) else None,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    if usage_callback is not None:
        usage_callback(response.usage)

    return extracted


async def extract_receipt(
    client: AsyncAnthropic,
    image_bytes: bytes,
    media_type: MediaType = "image/jpeg",
    *,
    model: str | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    usage_callback: Callable[[Usage], None] | None = None,
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
    model, usage_callback:
        Probe-only overrides (default None); the pinned default model is used
        when model is None.
    temperature:
        Defaults to DEFAULT_TEMPERATURE, which production relies on. Pass None
        to omit the key entirely - required for models that reject the
        parameter under a forced tool_choice.

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

    return await _call_claude(
        client,
        image_bytes,
        media_type,
        model=model,
        temperature=temperature,
        usage_callback=usage_callback,
    )
