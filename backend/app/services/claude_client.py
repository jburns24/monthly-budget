"""LLM client for receipt data extraction (Claude via OpenRouter).

Talks to OpenRouter's OpenAI-compatible chat completions API through the
AsyncOpenAI SDK, with tenacity retry logic layered on top of the SDK's built-in
retries (max_retries=2). Tenacity handles transient server errors (5xx, 429)
with exponential back-off; the SDK handles connection-level retries.

When settings.llm_mock is True, extract_receipt returns a deterministic
ExtractedReceipt based on settings.llm_mock_scenario without calling the API.
"""

import base64
import json
from collections.abc import Callable
from datetime import date
from typing import Literal

import httpx
from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from openai.types import CompletionUsage
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings
from app.logging import get_logger
from app.schemas.receipt import ExtractedReceipt

logger = get_logger(__name__)

# The model slug now lives in settings.llm_model (default anthropic/claude-haiku-5.5)
# so it can be changed per environment without a code change.
_MODEL = settings.llm_model
# Headroom for the date_reasoning field below. The extracted JSON itself is
# small, but truncating the tool input mid-object surfaces as a confusing
# model_validate failure rather than an obvious cap-hit, so leave slack.
_MAX_TOKENS = 2048

# Omitted from the request. Haiku 4.5 was pinned to 0.0 because its "which figure
# is the total" judgment on split-tender receipts was marginal under sampling.
# Haiku 5.5 returns a 400 for any temperature other than 1, so the key is left
# out entirely (None); pass a float only for a model that accepts it.
DEFAULT_TEMPERATURE: float | None = None

# Cap on the purchase description the model writes. It becomes the Expense
# description (String(500)) and the decision model's input (200-char request
# limit on the suggest endpoint), so keep it to one short line.
DESCRIPTION_MAX_CHARS = 120


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
The receipt is likely from this month ({today.strftime("%B %Y")}). Prefer the reading that \
places the purchase in the current month, or as close to today as possible, without going \
past today.
Find the transaction date - the date of purchase, not a "valid until", "printed on", or \
expiry date. Normalize it to YYYY-MM-DD. To disambiguate a numeric format: a leading \
value above 12 is the day; otherwise, if the receipt shows US cues (dollar amounts, a US \
address, a state abbreviation) read it as MM/DD/YYYY, and read it as DD/MM/YYYY \
otherwise.
Resolve the year in this order:
  - Expand a legible two-digit year to 20YY: 24 is 2024, 26 is 2026.
  - If the year is not printed at all, or is illegible, choose the most recent year that \
places the month and day on or before today's date.
  - If a four-digit year is legible but places the purchase outside this month, re-read \
the year digits carefully - confusing this year for last year is the common failure, and \
a receipt from another month is uncommon here. Prefer the most recent year that keeps the \
month and day on or before today unless the older year is unmistakably printed.
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

Phase 5 - Description.
Write one short line, under 100 characters, saying what was bought and where: the kind \
of purchase, up to three representative items in parentheses, then "at" and the store \
name from Phase 4. Base it on the itemized lines, not on the store's industry. Examples: \
"Groceries (milk, eggs, bread) at Safeway", "Dinner for two at Olive Garden", \
"Gas fill-up at Shell", "Kids' shoes and socks at Target". Leave out prices, totals, \
dates, card numbers, and loyalty details. If no items are legible, describe the \
purchase from the store alone ("Purchase at Home Depot"). Do not choose a budget \
category - that is decided separately from this description.

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
    "type": "function",
    "function": {
        "name": "extract_receipt",
        "description": "Extract structured data from a receipt image",
        "parameters": {
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
                        "One sentence: which field you read the date from, how you "
                        "resolved its year against today's date, and why the result "
                        "is in or near this month"
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
                "description": {
                    "type": ["string", "null"],
                    "description": (
                        "Short line saying what was bought and where, e.g. "
                        "'Groceries (milk, eggs, bread) at Safeway'; omit if not a receipt"
                    ),
                },
            },
            "required": ["is_receipt", "confidence"],
        },
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
            description="Groceries (milk, eggs, bread) at Test Market",
        ),
        "medium_confidence": ExtractedReceipt(
            is_receipt=True,
            confidence="medium",
            total_amount=42.50,
            date=None,
            store_name="Test Market",
            description="Groceries (milk, eggs, bread) at Test Market",
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


_MOCK_API_ERROR_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _get_mock_response(scenario: str) -> ExtractedReceipt:
    """Return a deterministic ExtractedReceipt for the given mock scenario.

    Raises APIStatusError for the 'api_error' scenario.
    Falls back to 'success' for unknown scenario names.
    """
    if scenario == "api_error":
        raise APIStatusError(
            "Mock LLM API error (scenario: api_error)",
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
    client: AsyncOpenAI,
    image_bytes: bytes,
    media_type: MediaType,
    *,
    model: str | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    usage_callback: Callable[[CompletionUsage], None] | None = None,
) -> ExtractedReceipt:
    """Send an image to Claude and parse the tool-use response. Wrapped by tenacity.

    ``model``/``usage_callback`` are probe-only overrides (see
    test-scripts/scan_receipt_probe.py); left as None the pinned default model
    is used. ``temperature`` defaults to DEFAULT_TEMPERATURE; None omits
    the key entirely, which is required for models that reject the parameter.
    """
    b64_data = base64.standard_b64encode(image_bytes).decode()

    logger.info("claude_extract_receipt_start", image_size=len(image_bytes), media_type=media_type)

    create_kwargs: dict = {}
    if temperature is not None:
        create_kwargs["temperature"] = temperature

    response = await client.chat.completions.create(
        model=model or settings.llm_model,
        max_tokens=_MAX_TOKENS,
        tools=[_TOOL_DEFINITION],
        tool_choice={"type": "function", "function": {"name": "extract_receipt"}},
        messages=[
            {"role": "system", "content": _build_system_prompt(date.today())},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64_data}"},
                    },
                    {"type": "text", "text": _USER_TEXT_PROMPT},
                ],
            },
        ],
        # Deliberately no provider.require_parameters: as of 2026-10 OpenRouter's
        # tool-compatibility filter rejects a *named* tool_choice for
        # anthropic/claude-haiku-5.5 on every endpoint (404 "No endpoints found
        # that support the provided 'tool_choice' value"), while the same request
        # without it is served by a first-party Claude host that honors the
        # forced tool. A provider that ignored it would surface as the
        # "no tool call" ValueError below, not as bad data.
        **create_kwargs,
    )

    choice = response.choices[0] if response.choices else None
    tool_calls = (choice.message.tool_calls if choice is not None else None) or []
    if not tool_calls:
        finish_reason = choice.finish_reason if choice is not None else None
        raise ValueError(f"LLM returned no tool call; finish_reason={finish_reason!r}")

    try:
        tool_input = json.loads(tool_calls[0].function.arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"LLM returned invalid tool call arguments: {exc}") from exc

    extracted = ExtractedReceipt.model_validate(tool_input)

    logger.info(
        "claude_extract_receipt_complete",
        is_receipt=extracted.is_receipt,
        confidence=extracted.confidence,
        has_total=extracted.total_amount is not None,
        has_date=extracted.date is not None,
        has_store=extracted.store_name is not None,
        has_description=extracted.description is not None,
        # Not persisted on the Receipt — it is scaffolding for the model, not
        # data — but it is the only way to tell a misread year from a mis-picked
        # one when a date comes back wrong.
        date_reasoning=tool_input.get("date_reasoning") if isinstance(tool_input, dict) else None,
        input_tokens=response.usage.prompt_tokens if response.usage else None,
        output_tokens=response.usage.completion_tokens if response.usage else None,
    )

    if usage_callback is not None and response.usage is not None:
        usage_callback(response.usage)

    return extracted


async def extract_receipt(
    client: AsyncOpenAI,
    image_bytes: bytes,
    media_type: MediaType = "image/jpeg",
    *,
    model: str | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    usage_callback: Callable[[CompletionUsage], None] | None = None,
) -> ExtractedReceipt:
    """Call Claude to extract structured data from a receipt image.

    When settings.llm_mock is True, returns a deterministic response
    for the scenario in settings.llm_mock_scenario without calling the API.

    Parameters
    ----------
    client:
        The AsyncOpenAI (OpenRouter) singleton from app.state.
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
        If the model returns no tool call, or unparseable tool arguments.
    """
    if settings.llm_mock:
        scenario = settings.llm_mock_scenario
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
