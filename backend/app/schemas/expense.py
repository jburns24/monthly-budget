"""Expense request/response Pydantic schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    """Request body for POST /api/expenses."""

    amount_cents: int = Field(gt=0)
    description: str = Field(default="", max_length=500)
    category_id: uuid.UUID
    expense_date: date


class ExpenseUpdate(BaseModel):
    """Request body for PUT /api/families/{family_id}/expenses/{expense_id}."""

    amount_cents: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=500)
    category_id: uuid.UUID | None = None
    expense_date: date | None = None
    expected_updated_at: datetime  # Required for optimistic locking


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
    category: CategoryBrief
    created_by_user: UserBrief = Field(validation_alias="user")
    amount_cents: int
    description: str
    expense_date: date
    created_at: datetime
    updated_at: datetime


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
    categories: list[BudgetCategorySummary]
    is_editable: bool = True  # False when grace period has expired for this month
