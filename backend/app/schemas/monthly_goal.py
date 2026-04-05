"""Monthly goal request/response Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MonthlyGoalCreate(BaseModel):
    """Request body for creating a single monthly goal."""

    category_id: uuid.UUID
    amount_cents: int = Field(gt=0)


class MonthlyGoalUpdate(BaseModel):
    """Request body for updating a monthly goal (optimistic locking via expected_version)."""

    amount_cents: int = Field(gt=0)
    expected_version: int


class MonthlyGoalResponse(BaseModel):
    """Response body for monthly goal endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    category_id: uuid.UUID
    year_month: str
    amount_cents: int
    version: int
    created_at: datetime
    updated_at: datetime


class BulkGoalsRequest(BaseModel):
    """Request body for bulk upsert of monthly goals for a given month."""

    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    goals: list[MonthlyGoalCreate]


class BulkGoalsResponse(BaseModel):
    """Response body for bulk goal upsert operations."""

    year_month: str
    created: int
    updated: int
    deleted: int
    goals: list[MonthlyGoalResponse]


class GoalsListResponse(BaseModel):
    """Response body listing monthly goals for a given month."""

    year_month: str
    goals: list[MonthlyGoalResponse]
    has_previous_goals: bool


class RolloverRequest(BaseModel):
    """Request body for the rollover endpoint."""

    source_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    target_month: str = Field(pattern=r"^\d{4}-\d{2}$")


class RolloverResponse(BaseModel):
    """Response body for the rollover endpoint."""

    copied_count: int
