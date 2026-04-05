"""Category request/response Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    """Request body for POST /api/categories."""

    name: str = Field(min_length=1, max_length=100)
    icon: str | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    """Request body for PATCH /api/categories/{category_id}."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    """Response body for category endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    name: str
    icon: str | None
    sort_order: int
    is_active: bool
    created_at: datetime


class CategoryDeleteResponse(BaseModel):
    """Response body for DELETE /api/categories/{category_id}."""

    message: str
    deleted: bool
    archived: bool = False
    expense_count: int = 0


class SeedResponse(BaseModel):
    """Response body for POST /api/categories/seed."""

    message: str
    created_count: int
