"""Family request/response Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class FamilyCreate(BaseModel):
    """Request body for POST /api/families."""

    name: str
    timezone: str = "America/New_York"


class FamilyMemberResponse(BaseModel):
    """A single member within a family response."""

    user_id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    role: str
    joined_at: datetime


class FamilyResponse(BaseModel):
    """Response body for GET /api/families/{family_id}."""

    id: uuid.UUID
    name: str
    timezone: str
    edit_grace_days: int
    created_by: uuid.UUID
    created_at: datetime
    members: list[FamilyMemberResponse]


class FamilyBrief(BaseModel):
    """Abbreviated family info included in UserResponse."""

    id: uuid.UUID
    name: str
    role: str


class InviteCreate(BaseModel):
    """Request body for POST /api/families/{family_id}/invites."""

    email: EmailStr


class InviteResponse(BaseModel):
    """Response body for a family invite."""

    id: uuid.UUID
    family_id: uuid.UUID
    family_name: str
    invited_by_name: str
    status: str
    created_at: datetime


class InviteAction(BaseModel):
    """Request body for POST /api/invites/{invite_id}/respond."""

    action: Literal["accept", "decline"]


class RoleUpdate(BaseModel):
    """Request body for PATCH /api/families/{family_id}/members/{user_id}/role."""

    role: Literal["admin", "member"]


class GenericMessage(BaseModel):
    """Generic success message response."""

    message: str
