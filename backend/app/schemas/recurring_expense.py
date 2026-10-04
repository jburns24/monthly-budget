"""Recurring expense request/response Pydantic schemas."""

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.expense import EntryType

Frequency = Literal["weekly", "biweekly", "monthly", "yearly"]


class RecurringExpenseCreate(BaseModel):
    """Request body for POST /api/families/{family_id}/recurring-expenses."""

    amount_cents: int = Field(gt=0)
    description: str = Field(default="", max_length=500)
    category_id: uuid.UUID | None = None
    entry_type: EntryType = "expense"
    frequency: Frequency
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        if self.entry_type == "expense" and self.category_id is None:
            raise ValueError("expense requires category_id")
        if self.entry_type == "income" and self.category_id is not None:
            raise ValueError("income must not have category_id")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class RecurringExpenseUpdate(BaseModel):
    """Request body for PUT /api/families/{family_id}/recurring-expenses/{rule_id}.

    Only fields present in the body change; ``end_date: null`` clears the end date.
    The entry type is fixed at creation — delete and recreate to change it.
    """

    amount_cents: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None
    frequency: Frequency | None = None
    end_date: date | None = None
    is_active: bool | None = None


class RecurringExpenseResponse(BaseModel):
    """Response body for recurring expense endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    category_id: uuid.UUID | None
    amount_cents: int
    description: str
    entry_type: EntryType
    frequency: Frequency
    start_date: date
    end_date: date | None
    next_due_date: date
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RecurringExpenseListResponse(BaseModel):
    """All recurring rules for a family."""

    recurring_expenses: list[RecurringExpenseResponse]
