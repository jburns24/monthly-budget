"""Receipt upload processing service — three-phase transaction.

Phase 1 (savepoint): validate MIME, sanitize image, insert
  Receipt(status='processing').
Phase 2 (non-atomic): call extract_receipt via AsyncAnthropic.
Phase 3 (savepoint): update Receipt + create Expense with suggested category.

The image itself is never stored — only the extraction result. Any failure marks
the Receipt 'failed' and the user re-uploads (there is nothing to retry from).
On a family with no active categories: mark Receipt 'failed', raise 409 — a
  parsed receipt must never complete without an Expense.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import cast

from anthropic import AsyncAnthropic
from anthropic.types import Usage
from fastapi import HTTPException

from app.logging import get_logger
from app.models.expense import Expense
from app.models.receipt import Receipt
from app.ports.unit_of_work import UnitOfWork
from app.schemas.receipt import ExtractedReceipt
from app.services import category_suggestion, claude_client, receipt_storage

logger = get_logger(__name__)


# A purchase cannot happen in the future, but `date.today()` here is the
# container's UTC day, which can already be tomorrow relative to the uploader's
# local day. One day of slack keeps a genuine same-day receipt from being
# thrown away over timezone skew.
_FUTURE_DATE_SLACK = timedelta(days=1)

# The model has no clock and often resolves a missing/ambiguous year against
# training-data priors, landing this year's purchase under last year. Dates
# older than this window are treated as a misread year and snapped forward to
# the most recent occurrence of the same month/day on or before today.
_STALE_DATE_SLACK = timedelta(days=365)


def _most_recent_occurrence(month: int, day: int, today: date) -> date | None:
    """Return the latest month/day on or before today, or None if none exists."""
    for year in (today.year, today.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate <= today:
            return candidate
    return None


def _parse_expense_date(date_str: str | None) -> date | None:
    """Parse a trustworthy YYYY-MM-DD from Claude, or None when there isn't one.

    Returns None for a missing, unparseable, or impossible date; the caller
    substitutes today and leaves ``Receipt.parsed_date`` unset, so "we could not
    read a date" stays distinguishable from "the receipt is dated today".

    Two deterministic backstops cover soft prompt failures:
    - A date past today (plus a day of UTC skew slack) is treated as unread.
    - A date older than ``_STALE_DATE_SLACK`` has its year snapped to the most
      recent occurrence of the same month/day on or before today — the common
      prod failure is filing this year's purchase under last year.
    """
    if date_str is None:
        return None
    try:
        parsed = date.fromisoformat(date_str)
    except ValueError:
        logger.warning("receipt_date_parse_error", raw=date_str)
        return None
    today = date.today()
    if parsed - today > _FUTURE_DATE_SLACK:
        logger.warning("receipt_date_in_future", raw=date_str)
        return None
    if today - parsed >= _STALE_DATE_SLACK:
        remapped = _most_recent_occurrence(parsed.month, parsed.day, today)
        if remapped is not None and remapped != parsed:
            logger.warning(
                "receipt_date_stale_year_corrected",
                raw=date_str,
                corrected=remapped.isoformat(),
            )
            return remapped
    return parsed


def _amount_cents(total_amount: float | None) -> int | None:
    """Convert Claude's total_amount (float dollars) to cents integer, or None."""
    if total_amount is None or total_amount <= 0:
        return None
    return max(1, round(total_amount * 100))


async def _mark_failed(uow: UnitOfWork, receipt: Receipt, reason: str) -> None:
    """Update receipt to failed status.

    Commits the unit of work so the audit row persists even though the caller is
    about to raise an HTTPException (which would otherwise trigger ``get_db``'s
    rollback and wipe both the Phase-1 insert and this status update). The spec
    requires that the Receipt row is durable with ``status='failed'`` so the
    retry flow and audit trail can function.

    This is the only place in the codebase that calls
    ``UnitOfWork.commit`` — the rule everywhere else is that ``get_db``'s
    teardown owns the commit. See ``docs/data-layer-ports-design.md`` section 2.
    """
    try:
        async with uow.savepoint():
            receipt.status = "failed"
            receipt.error_message = reason[:500]
            await uow.flush()
        await uow.commit()
    except Exception:
        logger.warning("receipt_mark_failed_db_error", receipt_id=str(receipt.id))


async def _run_phase3(
    uow: UnitOfWork,
    receipt: Receipt,
    extracted: ExtractedReceipt,
    family_id: uuid.UUID,
    uploader_id: uuid.UUID,
) -> tuple[Expense, bool]:
    """Phase 3: update Receipt fields + create Expense. Returns (expense, needs_edit)."""
    parsed_date = _parse_expense_date(extracted.date)
    expense_date = parsed_date if parsed_date is not None else date.today()
    total_cents = _amount_cents(extracted.total_amount)
    # Tracked separately from needs_edit: this one governs whether the amount is
    # trustworthy, and it alone decides the amount_cents=0 placeholder below.
    unusable_amount = extracted.confidence == "low" or total_cents is None
    year_month = expense_date.strftime("%Y-%m")
    description = extracted.store_name or "Unknown merchant"

    # A successfully parsed receipt must always yield an Expense (spec §Unit 3).
    # suggest_for_store returns None whenever neither name similarity nor recent
    # usage matches — common for a low-confidence extraction with no store name —
    # so degrade to any active category rather than completing with no expense.
    suggested_category = await category_suggestion.suggest_for_store(
        uow.categories,
        family_id,
        extracted.store_name or "",
        category_hint=extracted.category,
    )
    category_is_fallback = suggested_category is None
    if suggested_category is None:
        # Last-resort pick, ordered by (sort_order, name). suggest_for_store
        # deliberately returns None when neither name similarity nor 90-day usage
        # matches — the right answer to "which category best fits this store?" —
        # but a receipt upload still has to produce an Expense.
        suggested_category = await uow.categories.first_active(family_id)
    if suggested_category is None:
        # expenses.category_id is NOT NULL, so there is nothing to attach the
        # expense to. Fail loudly instead of reporting success with an empty
        # expense list. The user re-uploads once the family creates a category.
        await _mark_failed(uow, receipt, "No active categories available to categorize the expense")
        logger.warning("receipt_phase3_no_active_categories", receipt_id=str(receipt.id), family_id=str(family_id))
        raise HTTPException(
            status_code=409,
            detail="No active categories. Create a category, then retry this receipt.",
        )

    # first_active is an arbitrary pick, not a match on the store name, so the
    # user has to confirm it even when the extraction itself was clean.
    needs_edit = unusable_amount or category_is_fallback

    expense: Expense

    try:
        async with uow.savepoint():
            receipt.status = "completed"
            # Left None when the date was missing, unparseable, or impossible —
            # the expense still gets today's date, but the review UI keys its
            # "no date found, defaulted to today" hint off this being unset and
            # must not be told a fallback was read off the receipt.
            receipt.parsed_date = parsed_date
            receipt.parsed_total_cents = total_cents
            receipt.parsed_merchant = extracted.store_name
            receipt.raw_response = extracted.model_dump()
            receipt.error_message = None

            now = datetime.now(tz=timezone.utc)
            # Spec §Unit 3: low-confidence or missing-total extractions persist
            # with amount_cents=0 so the frontend "Needs review" chip fires
            # (keyed on receipt_status == 'completed' && amount_cents == 0).
            # Keyed on unusable_amount, not needs_edit: a clean extraction that
            # only fell back on the category keeps its real total.
            # When unusable_amount is False, total_cents is guaranteed not None.
            expense_amount_cents: int = 0 if unusable_amount else cast(int, total_cents)
            expense = Expense(
                family_id=family_id,
                user_id=uploader_id,
                category_id=suggested_category.id,
                amount_cents=expense_amount_cents,
                description=description,
                expense_date=expense_date,
                year_month=year_month,
                receipt_id=receipt.id,
                created_at=now,
                updated_at=now,
            )
            uow.expenses.add(expense)

            await uow.flush()

    except Exception as exc:
        await _mark_failed(uow, receipt, f"DB error in phase 3: {exc}")
        logger.error("receipt_phase3_failed", receipt_id=str(receipt.id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Receipt processing failed. Try again or enter manually.",
        ) from exc

    logger.info(
        "receipt_phase3_complete",
        receipt_id=str(receipt.id),
        expense_id=str(expense.id),
        needs_edit=needs_edit,
    )

    return expense, needs_edit


async def process_upload(
    uow: UnitOfWork,
    anthropic_client_inst: AsyncAnthropic,
    family_id: uuid.UUID,
    uploader_id: uuid.UUID,
    raw_bytes: bytes,
    *,
    model: str | None = None,
    temperature: float | None = claude_client.DEFAULT_TEMPERATURE,
    usage_callback: Callable[[Usage], None] | None = None,
) -> tuple[Receipt, Expense, bool]:
    """Process a receipt image upload through the three-phase pipeline.

    ``model``/``temperature``/``usage_callback`` are forwarded to
    ``claude_client.extract_receipt``. ``model``/``usage_callback`` are
    probe-only overrides (see test-scripts/scan_receipt_probe.py); temperature
    defaults to the pinned DEFAULT_TEMPERATURE that production relies on, and
    passing None omits the key for models that reject it.

    Returns
    -------
    tuple[Receipt, Expense, bool]
        ``(receipt, expense, needs_edit)`` where ``needs_edit`` is True when
        Claude had low confidence, could not extract the total, or no category
        matched the store name (leaving the expense on an arbitrary fallback
        category the user should confirm). A successful return always carries
        an Expense. Note that ``needs_edit`` does not imply ``amount_cents == 0``
        — only the first two causes zero the amount.

    Raises
    ------
    HTTPException(415)
        Unsupported MIME type.
    HTTPException(400)
        Corrupt or unparseable image.
    HTTPException(422)
        Image is not a receipt.
    HTTPException(409)
        Family has no active categories to attach the expense to.
    HTTPException(503)
        Claude API error or unexpected processing failure.
    """
    # --- Pre-phase: validate + sanitize (pure compute, no side effects) ---
    try:
        receipt_storage.validate_mime(raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    try:
        sanitized_bytes, _ = receipt_storage.sanitize_image(raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc

    # --- Phase 1: insert Receipt(status=processing) ---
    receipt: Receipt

    try:
        async with uow.savepoint():
            receipt = Receipt(
                family_id=family_id,
                uploaded_by=uploader_id,
                status="processing",
            )
            uow.receipts.add(receipt)
            await uow.flush()

    except Exception as exc:
        logger.error("receipt_phase1_failed", family_id=str(family_id), error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to save receipt") from exc

    logger.info(
        "receipt_phase1_complete",
        receipt_id=str(receipt.id),
        family_id=str(family_id),
        image_size=len(sanitized_bytes),
    )

    # --- Phase 2: call Claude (non-atomic) ---
    extracted: ExtractedReceipt

    try:
        extracted = await claude_client.extract_receipt(
            anthropic_client_inst,
            sanitized_bytes,
            media_type="image/jpeg",
            model=model,
            temperature=temperature,
            usage_callback=usage_callback,
        )
    except Exception as exc:
        await _mark_failed(uow, receipt, f"Claude API error: {exc}")
        logger.error("receipt_phase2_failed", receipt_id=str(receipt.id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Receipt processing failed. Try again or enter manually.",
        ) from exc

    # Non-receipt: reject
    if not extracted.is_receipt:
        await _mark_failed(uow, receipt, "Not a receipt")
        logger.info("receipt_not_a_receipt", receipt_id=str(receipt.id))
        raise HTTPException(
            status_code=422,
            detail="This doesn't appear to be a receipt. Please try again or enter manually.",
        )

    logger.info(
        "receipt_phase2_complete",
        receipt_id=str(receipt.id),
        confidence=extracted.confidence,
        has_total=extracted.total_amount is not None,
        has_date=extracted.date is not None,
    )

    expense, needs_edit = await _run_phase3(uow, receipt, extracted, family_id, uploader_id)
    return receipt, expense, needs_edit
