"""Receipt request/response Pydantic schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReceiptStatus = Literal["processing", "completed", "failed"]


class ExtractedReceipt(BaseModel):
    """Data extracted by Claude from a receipt image."""

    is_receipt: bool
    confidence: Literal["high", "medium", "low"]
    total_amount: float | None = None
    date: str | None = None
    store_name: str | None = None


class ReceiptResponse(BaseModel):
    """Response body for a single receipt."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    uploaded_by: uuid.UUID
    image_path: str | None
    raw_response: dict | None
    parsed_date: date | None
    parsed_total_cents: int | None
    parsed_merchant: str | None
    status: ReceiptStatus
    error_message: str | None
    created_at: datetime


class ReceiptUploadResponse(BaseModel):
    """Response body for POST /api/families/{family_id}/receipts."""

    receipt: ReceiptResponse
    expense_id: uuid.UUID | None = None
    needs_edit: bool = False


class ReceiptListQuery(BaseModel):
    """Query parameters for GET /api/families/{family_id}/receipts."""

    status: ReceiptStatus | None = None
    uploaded_by: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
