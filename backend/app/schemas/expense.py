"""Expense request/response Pydantic schemas."""

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.receipt import ReceiptStatus

EntryType = Literal["expense", "income"]


def _coerce_starting_balance_entry_type(data: object) -> object:
    """Starting balance implies income; an explicit expense entry_type is rejected."""
    if not isinstance(data, dict):
        return data
    if not data.get("is_starting_balance"):
        return data
    if data.get("entry_type") == "expense":
        raise ValueError("is_starting_balance requires entry_type to be 'income'")
    data["entry_type"] = "income"
    return data


class ExpenseCreate(BaseModel):
    """Request body for POST /api/expenses."""

    amount_cents: int = Field(gt=0)
    description: str = Field(default="", max_length=500)
    category_id: uuid.UUID | None = None
    expense_date: date
    entry_type: EntryType = "expense"
    is_starting_balance: bool = False

    @model_validator(mode="before")
    @classmethod
    def coerce_starting_balance(cls, data: object) -> object:
        return _coerce_starting_balance_entry_type(data)

    @model_validator(mode="after")
    def validate_entry_category_rules(self) -> Self:
        if self.entry_type == "expense" and self.category_id is None:
            raise ValueError("expense requires category_id")
        if self.entry_type == "income" and self.category_id is not None:
            raise ValueError("income must not have category_id")
        return self


class ExpenseUpdate(BaseModel):
    """Request body for PUT /api/families/{family_id}/expenses/{expense_id}."""

    amount_cents: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None
    expense_date: date | None = None
    entry_type: EntryType | None = None
    is_starting_balance: bool | None = None
    expected_updated_at: datetime  # Required for optimistic locking

    @model_validator(mode="before")
    @classmethod
    def coerce_starting_balance(cls, data: object) -> object:
        return _coerce_starting_balance_entry_type(data)

    @model_validator(mode="after")
    def validate_entry_category_rules(self) -> Self:
        if self.entry_type == "income" and self.category_id is not None:
            raise ValueError("income must not have category_id")
        if self.entry_type == "expense" and "category_id" in self.model_fields_set and self.category_id is None:
            raise ValueError("expense requires category_id")
        return self


class CategoryBrief(BaseModel):
    """Nested category info embedded in expense responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    icon: str | None


class UserBrief(BaseModel):
    """Nested user info embedded in expense responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str


class ExpenseResponse(BaseModel):
    """Response body for expense endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    category: CategoryBrief | None
    created_by_user: UserBrief = Field(validation_alias="user")
    amount_cents: int
    description: str
    expense_date: date
    created_at: datetime
    updated_at: datetime
    entry_type: EntryType
    is_starting_balance: bool
    receipt_id: uuid.UUID | None = None
    receipt_status: ReceiptStatus | None = None


class ExpenseListResponse(BaseModel):
    """Paginated list of expenses."""

    expenses: list[ExpenseResponse]
    total_count: int
    page: int
    per_page: int


class BudgetCategorySummary(BaseModel):
    """Per-category spending summary within a budget period."""

    category_id: uuid.UUID
    category_name: str
    icon: str | None
    spent_cents: int
    goal_cents: int | None
    percentage: float
    status: str


class BudgetSummaryResponse(BaseModel):
    """Overall budget summary for a given month."""

    year_month: str  # e.g. "2026-04"
    total_spent_cents: int
    total_income_cents: int = 0  # Populated by Slice B; default 0 until then
    categories: list[BudgetCategorySummary]
    is_editable: bool = True  # False when grace period has expired for this month
