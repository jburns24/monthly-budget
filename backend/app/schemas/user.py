"""User request/response Pydantic schemas."""

import uuid

from pydantic import BaseModel


class UserResponse(BaseModel):
    """Response body for GET /api/me."""

    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    timezone: str


class UserUpdate(BaseModel):
    """Request body for PUT /api/me."""

    display_name: str | None = None
    timezone: str | None = None
