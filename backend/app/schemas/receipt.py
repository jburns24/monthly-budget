"""Receipt request/response Pydantic schemas."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

ReceiptStatus = Literal["processing", "completed", "failed"]

# Stand-ins a language model reaches for when a field is unreadable but the tool
# schema types it as something other than null.
_NULL_SENTINELS = frozenset({"", "null", "none", "nil", "n/a", "na", "unknown", "-", "—"})


def _sentinel_to_none(value: Any) -> Any:
    """Normalize a stringified stand-in for null into a real ``None``.

    Observed against Haiku 4.5: for a field the model cannot read it emits the
    literal string ``"null"``, which fails float parsing and turns a receipt
    upload into a 503. On ``date`` the failure is quieter and worse — ``"null"``
    validates fine as a string, then ``_parse_expense_date`` cannot parse it and
    silently substitutes today's date, so the expense lands on the wrong day.
    Coercing here keeps a legitimate "I could not read this" answer on the
    intended ``None`` path instead of either outcome.
    """
    if isinstance(value, str) and value.strip().lower() in _NULL_SENTINELS:
        return None
    return value


NullableStr = Annotated[str | None, BeforeValidator(_sentinel_to_none)]
NullableFloat = Annotated[float | None, BeforeValidator(_sentinel_to_none)]


class ExtractedReceipt(BaseModel):
    """Data extracted by Claude from a receipt image.

    The wire keys Claude emits are ``name``/``total``; the Python attributes keep
    the longer ``store_name``/``total_amount`` names the rest of the pipeline
    already reads. ``populate_by_name`` lets both spellings construct the model,
    so mock scenarios and tests can keep using keyword arguments.

    These are ``validation_alias`` rather than ``alias`` deliberately. Both
    accept the wire keys, but a plain ``alias`` also renames the parameter in
    the ``__init__`` that PEP 681 ``dataclass_transform`` synthesizes for type
    checkers, and that synthesis has no notion of ``populate_by_name`` — so
    every ``total_amount=``/``store_name=`` keyword in the mocks and tests
    became a type error even though it works at runtime.

    Note ``model_dump()`` serializes under the *field* names, not the aliases —
    ``Receipt.raw_response`` therefore keeps the shape it has always had.
    """

    model_config = ConfigDict(populate_by_name=True)

    is_receipt: bool
    confidence: Literal["high", "medium", "low"]
    total_amount: NullableFloat = Field(default=None, validation_alias="total")
    date: NullableStr = None
    store_name: NullableStr = Field(default=None, validation_alias="name")
    category: NullableStr = None


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
