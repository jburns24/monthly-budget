"""Receipts router: upload, list, get, image, retry, and delete endpoints."""

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_anthropic_client, require_family_member
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.receipt import Receipt
from app.models.user import User
from app.schemas.receipt import ReceiptResponse, ReceiptStatus, ReceiptUploadResponse
from app.services import rate_limiter, receipt_service, receipt_storage

logger = get_logger(__name__)

router = APIRouter(prefix="/api/families/{family_id}/receipts", tags=["receipts"])

MAX_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_receipt_or_404(db: AsyncSession, family_id: uuid.UUID, receipt_id: uuid.UUID) -> Receipt:
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_id, Receipt.family_id == family_id))
    receipt = result.scalar_one_or_none()
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return receipt


async def _check_rate_limit(family_id: uuid.UUID) -> None:
    allowed, _ = await rate_limiter.check_and_increment_receipt_upload(family_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily upload limit reached. Try again tomorrow.",
            headers={"Retry-After": "86400"},
        )


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/receipts — upload
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ReceiptUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt(
    family_id: uuid.UUID,
    file: UploadFile,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    anthropic: Annotated[AsyncAnthropic, Depends(get_anthropic_client)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _rate_limit: Annotated[None, Depends(_check_rate_limit)],
) -> ReceiptUploadResponse:
    """Upload a receipt image and extract expense data via Claude."""
    current_user, _member = membership

    raw_bytes = await file.read(MAX_BYTES + 1)
    if len(raw_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 5MB.",
        )

    receipt, expense, needs_edit = await receipt_service.process_upload(
        db, anthropic, family_id, current_user.id, raw_bytes
    )
    await db.commit()

    logger.info(
        "receipt_upload_complete",
        receipt_id=str(receipt.id),
        family_id=str(family_id),
        has_expense=expense is not None,
        needs_edit=needs_edit,
    )

    return ReceiptUploadResponse(
        receipt=ReceiptResponse.model_validate(receipt),
        expense_id=expense.id if expense else None,
        needs_edit=needs_edit,
    )


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts — list
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    family_id: uuid.UUID,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    receipt_status: ReceiptStatus | None = Query(default=None, alias="status"),
    uploaded_by: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> list[ReceiptResponse]:
    """List receipts for a family with optional filters."""
    stmt = select(Receipt).where(Receipt.family_id == family_id)

    if receipt_status is not None:
        stmt = stmt.where(Receipt.status == receipt_status)
    if uploaded_by is not None:
        stmt = stmt.where(Receipt.uploaded_by == uploaded_by)
    if date_from is not None:
        stmt = stmt.where(Receipt.parsed_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Receipt.parsed_date <= date_to)

    stmt = stmt.order_by(Receipt.created_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    receipts = result.scalars().all()
    return [ReceiptResponse.model_validate(r) for r in receipts]


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts/{receipt_id} — get one
# ---------------------------------------------------------------------------


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    family_id: uuid.UUID,
    receipt_id: uuid.UUID,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReceiptResponse:
    """Get a single receipt by ID."""
    receipt = await _get_receipt_or_404(db, family_id, receipt_id)
    return ReceiptResponse.model_validate(receipt)


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts/{receipt_id}/image — stream image
# ---------------------------------------------------------------------------


@router.get("/{receipt_id}/image")
async def get_receipt_image(
    family_id: uuid.UUID,
    receipt_id: uuid.UUID,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream the raw image bytes for a receipt. Returns 410 if file is missing."""
    receipt = await _get_receipt_or_404(db, family_id, receipt_id)

    if not receipt.image_path:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Image no longer available.")

    image_path = Path(receipt.image_path)
    try:
        image_bytes = await receipt_storage.load(image_path)
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Image file not found.")

    return StreamingResponse(
        iter([image_bytes]),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/receipts/{receipt_id}/retry
# ---------------------------------------------------------------------------


@router.post("/{receipt_id}/retry", response_model=ReceiptUploadResponse)
async def retry_receipt(
    family_id: uuid.UUID,
    receipt_id: uuid.UUID,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    anthropic: Annotated[AsyncAnthropic, Depends(get_anthropic_client)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReceiptUploadResponse:
    """Re-run Claude extraction for a failed receipt.

    Returns 409 if the receipt is not in ``status='failed'``. Uses optimistic
    locking (``UPDATE ... WHERE status='failed' RETURNING``) so that two
    concurrent retries on the same receipt cannot both proceed — exactly one
    caller wins the row-level UPDATE, the other gets 409. See spec Open
    Question #2.
    """
    receipt = await _get_receipt_or_404(db, family_id, receipt_id)

    # Atomic failed->processing transition (raises 409 on non-failed rows).
    receipt = await receipt_service.claim_receipt_for_retry(db, receipt)

    receipt, expense, needs_edit = await receipt_service.reprocess_receipt(db, anthropic, receipt)
    await db.commit()

    logger.info(
        "receipt_retry_complete",
        receipt_id=str(receipt.id),
        family_id=str(family_id),
        needs_edit=needs_edit,
    )

    return ReceiptUploadResponse(
        receipt=ReceiptResponse.model_validate(receipt),
        expense_id=expense.id if expense else None,
        needs_edit=needs_edit,
    )


# ---------------------------------------------------------------------------
# DELETE /api/families/{family_id}/receipts/{receipt_id}
# ---------------------------------------------------------------------------


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    family_id: uuid.UUID,
    receipt_id: uuid.UUID,
    membership: Annotated[tuple[User, FamilyMember], Depends(require_family_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a receipt. Authorized for the uploader or any family admin."""
    current_user, member = membership
    receipt = await _get_receipt_or_404(db, family_id, receipt_id)

    if receipt.uploaded_by != current_user.id and member.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the uploader or a family admin can delete this receipt.",
        )

    if receipt.image_path:
        await receipt_storage.delete(Path(receipt.image_path))

    await db.delete(receipt)
    await db.commit()

    logger.info("receipt_deleted", receipt_id=str(receipt_id), user_id=str(current_user.id))
