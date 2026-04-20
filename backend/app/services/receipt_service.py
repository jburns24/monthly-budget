"""Receipt upload processing service — three-phase transaction.

Phase 1 (savepoint): validate MIME, sanitize image, save to disk, insert
  Receipt(status='processing').
Phase 2 (non-atomic): call extract_receipt via AsyncAnthropic.
Phase 3 (savepoint): update Receipt + create Expense with suggested category.

On any Phase 2/3 failure: mark Receipt 'failed', delete image, propagate error.
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
    """Update receipt to failed status and delete the image file."""
    try:
        async with db.begin_nested():
            receipt.status = "failed"
            receipt.error_message = reason[:500]
            await db.flush()
    except Exception:
        logger.warning("receipt_mark_failed_db_error", receipt_id=str(receipt.id))

    if image_path is not None:
        await receipt_storage.delete(image_path)


async def process_upload(
    db: AsyncSession,
    anthropic_client_inst: AsyncAnthropic,
    family_id: uuid.UUID,
    uploader_id: uuid.UUID,
    raw_bytes: bytes,
) -> tuple[Receipt, Expense | None, bool]:
    """Process a receipt image upload through the three-phase pipeline.

    Parameters
    ----------
    db:
        Active async session. Caller is responsible for committing.
    anthropic_client_inst:
        AsyncAnthropic singleton from app.state.
    family_id:
        UUID of the owning family.
    uploader_id:
        UUID of the user uploading the receipt.
    raw_bytes:
        Raw image bytes from the multipart upload.

    Returns
    -------
    tuple[Receipt, Expense | None, bool]
        ``(receipt, expense_or_None, needs_edit)`` where ``needs_edit`` is True
        when Claude had low confidence or could not extract the total.

    Raises
    ------
    HTTPException(422)
        MIME validation failure or image is not a receipt.
    HTTPException(503)
        Claude API error or unexpected processing failure.
    """
    # --- Pre-phase: validate + sanitize (pure compute, no side effects) ---
    try:
        receipt_storage.validate_mime(raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        sanitized_bytes, _ = receipt_storage.sanitize_image(raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid image: {exc}") from exc

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
        await _mark_failed(db, receipt, image_path, f"Claude API error: {exc}")
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

    # --- Phase 3: update Receipt + create Expense ---
    expense_date = _parse_expense_date(extracted.date)
    total_cents = _amount_cents(extracted.total_amount)
    needs_edit = extracted.confidence == "low" or total_cents is None
    year_month = expense_date.strftime("%Y-%m")
    description = extracted.store_name or "Unknown merchant"

    # Suggest category from store name; fall back to any active category
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

    return receipt, expense, needs_edit
