"""Receipt upload processing service — three-phase transaction.

Phase 1 (savepoint): validate MIME, sanitize image, save to disk, insert
  Receipt(status='processing').
Phase 2 (non-atomic): call extract_receipt via AsyncAnthropic.
Phase 3 (savepoint): update Receipt + create Expense with suggested category.

On Phase 2 Claude errors: mark Receipt 'failed', preserve image for retry.
On non-receipt / Phase 3 errors: mark Receipt 'failed', delete image.
"""

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from anthropic import AsyncAnthropic
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.expense import Expense
from app.models.receipt import Receipt
from app.schemas.receipt import ExtractedReceipt
from app.services import category_suggestion, claude_client, receipt_storage

logger = get_logger(__name__)


def _parse_expense_date(date_str: str | None) -> date:
    """Parse YYYY-MM-DD string from Claude; fall back to today on None or parse error."""
    if date_str is not None:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            logger.warning("receipt_date_parse_error", raw=date_str)
    return date.today()


def _amount_cents(total_amount: float | None) -> int | None:
    """Convert Claude's total_amount (float dollars) to cents integer, or None."""
    if total_amount is None or total_amount <= 0:
        return None
    return max(1, round(total_amount * 100))


async def _mark_failed(db: AsyncSession, receipt: Receipt, image_path: Path | None, reason: str) -> None:
    """Update receipt to failed status and optionally delete the image file."""
    try:
        async with db.begin_nested():
            receipt.status = "failed"
            receipt.error_message = reason[:500]
            await db.flush()
    except Exception:
        logger.warning("receipt_mark_failed_db_error", receipt_id=str(receipt.id))

    if image_path is not None:
        await receipt_storage.delete(image_path)


async def _run_phase3(
    db: AsyncSession,
    receipt: Receipt,
    extracted: ExtractedReceipt,
    family_id: uuid.UUID,
    uploader_id: uuid.UUID,
    image_path: Path | None,
) -> tuple[Expense | None, bool]:
    """Phase 3: update Receipt fields + create Expense. Returns (expense, needs_edit)."""
    expense_date = _parse_expense_date(extracted.date)
    total_cents = _amount_cents(extracted.total_amount)
    needs_edit = extracted.confidence == "low" or total_cents is None
    year_month = expense_date.strftime("%Y-%m")
    description = extracted.store_name or "Unknown merchant"

    suggested_category = None
    if extracted.store_name:
        suggested_category = await category_suggestion.suggest_for_store(db, family_id, extracted.store_name)
    if suggested_category is None:
        suggested_category = await category_suggestion.suggest_for_store(db, family_id, "")

    expense: Expense | None = None

    try:
        async with db.begin_nested():
            receipt.status = "completed"
            receipt.parsed_date = expense_date if extracted.date else None
            receipt.parsed_total_cents = total_cents
            receipt.parsed_merchant = extracted.store_name
            receipt.raw_response = extracted.model_dump()
            receipt.error_message = None

            if suggested_category is not None:
                now = datetime.now(tz=timezone.utc)
                expense = Expense(
                    family_id=family_id,
                    user_id=uploader_id,
                    category_id=suggested_category.id,
                    amount_cents=total_cents if total_cents is not None else 1,
                    description=description,
                    expense_date=expense_date,
                    year_month=year_month,
                    receipt_id=receipt.id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(expense)

            await db.flush()

    except Exception as exc:
        await _mark_failed(db, receipt, image_path, f"DB error in phase 3: {exc}")
        logger.error("receipt_phase3_failed", receipt_id=str(receipt.id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Receipt processing failed. Try again or enter manually.",
        ) from exc

    logger.info(
        "receipt_phase3_complete",
        receipt_id=str(receipt.id),
        expense_id=str(expense.id) if expense else None,
        needs_edit=needs_edit,
    )

    return expense, needs_edit


async def process_upload(
    db: AsyncSession,
    anthropic_client_inst: AsyncAnthropic,
    family_id: uuid.UUID,
    uploader_id: uuid.UUID,
    raw_bytes: bytes,
) -> tuple[Receipt, Expense | None, bool]:
    """Process a receipt image upload through the three-phase pipeline.

    Returns
    -------
    tuple[Receipt, Expense | None, bool]
        ``(receipt, expense_or_None, needs_edit)`` where ``needs_edit`` is True
        when Claude had low confidence or could not extract the total.

    Raises
    ------
    HTTPException(415)
        Unsupported MIME type.
    HTTPException(400)
        Corrupt or unparseable image.
    HTTPException(422)
        Image is not a receipt.
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

    # --- Phase 1: save image + insert Receipt(status=processing) ---
    image_path: Path | None = None
    receipt: Receipt

    try:
        image_path = await receipt_storage.save(family_id, sanitized_bytes, ".jpg")

        async with db.begin_nested():
            receipt = Receipt(
                family_id=family_id,
                uploaded_by=uploader_id,
                image_path=str(image_path),
                status="processing",
            )
            db.add(receipt)
            await db.flush()

    except Exception as exc:
        if image_path is not None:
            await receipt_storage.delete(image_path)
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
        )
    except Exception as exc:
        # Keep image on disk so the retry endpoint can re-run extraction.
        await _mark_failed(db, receipt, None, f"Claude API error: {exc}")
        logger.error("receipt_phase2_failed", receipt_id=str(receipt.id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Receipt processing failed. Try again or enter manually.",
        ) from exc

    # Non-receipt: clean up and reject
    if not extracted.is_receipt:
        await _mark_failed(db, receipt, image_path, "Not a receipt")
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

    expense, needs_edit = await _run_phase3(db, receipt, extracted, family_id, uploader_id, image_path)
    return receipt, expense, needs_edit


async def reprocess_receipt(
    db: AsyncSession,
    anthropic_client_inst: AsyncAnthropic,
    receipt: Receipt,
) -> tuple[Receipt, Expense | None, bool]:
    """Re-run Phase 2 + Phase 3 for an existing failed receipt.

    Used by the retry endpoint. Loads the image from ``receipt.image_path``.

    Raises
    ------
    HTTPException(422)
        Image file missing or no longer on disk.
    HTTPException(422)
        Claude determines image is not a receipt.
    HTTPException(503)
        Claude API error or Phase 3 DB failure.
    """
    if not receipt.image_path:
        raise HTTPException(status_code=422, detail="Image no longer available. Please re-upload.")

    image_path = Path(receipt.image_path)
    try:
        image_bytes = await receipt_storage.load(image_path)
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=422, detail="Image file missing. Please re-upload.")

    # Phase 2: call Claude
    try:
        extracted = await claude_client.extract_receipt(
            anthropic_client_inst,
            image_bytes,
            media_type="image/jpeg",
        )
    except Exception as exc:
        await _mark_failed(db, receipt, None, f"Claude API error: {exc}")
        logger.error("receipt_retry_phase2_failed", receipt_id=str(receipt.id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Receipt processing failed. Try again or enter manually.",
        ) from exc

    if not extracted.is_receipt:
        await _mark_failed(db, receipt, image_path, "Not a receipt")
        logger.info("receipt_retry_not_a_receipt", receipt_id=str(receipt.id))
        raise HTTPException(
            status_code=422,
            detail="This doesn't appear to be a receipt. Please try again or enter manually.",
        )

    expense, needs_edit = await _run_phase3(db, receipt, extracted, receipt.family_id, receipt.uploaded_by, image_path)
    return receipt, expense, needs_edit
