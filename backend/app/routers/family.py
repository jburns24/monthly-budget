"""Family router: family CRUD, invite management, and member management endpoints."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.dependencies import get_current_user, require_family_admin, require_family_member
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.user import User
from app.schemas.family import (
    FamilyCreate,
    FamilyMemberResponse,
    FamilyResponse,
    GenericMessage,
    InviteAction,
    InviteCreate,
    InviteResponse,
    RoleUpdate,
)
from app.services import family_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["families"])


def _family_to_response(family) -> FamilyResponse:
    """Convert a Family ORM object (with eager-loaded members) to FamilyResponse."""
    return FamilyResponse(
        id=family.id,
        name=family.name,
        timezone=family.timezone,
        edit_grace_days=family.edit_grace_days,
        created_by=family.created_by,
        created_at=family.created_at,
        members=[
            FamilyMemberResponse(
                user_id=m.user_id,
                email=m.user.email,
                display_name=m.user.display_name,
                avatar_url=m.user.avatar_url,
                role=m.role,
                joined_at=m.joined_at,
            )
            for m in family.members
        ],
    )


@router.post("/families", response_model=FamilyResponse, status_code=status.HTTP_201_CREATED)
async def create_family(
    body: FamilyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyResponse:
    """Create a new family with the current user as admin owner."""
    family = await family_service.create_family(db, current_user, body.name, body.timezone)
    # Re-fetch with members eager-loaded for response
    family = await family_service.get_family_with_members(db, family.id)
    logger.info("family_created_endpoint", family_id=str(family.id), user_id=str(current_user.id))
    return _family_to_response(family)


@router.get("/families/{family_id}", response_model=FamilyResponse, status_code=status.HTTP_200_OK)
async def get_family(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    db: AsyncSession = Depends(get_db),
) -> FamilyResponse:
    """Get family details with all members."""
    family = await family_service.get_family_with_members(db, family_id)
    return _family_to_response(family)


@router.post("/families/{family_id}/invites", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def invite_to_family(
    family_id: uuid.UUID,
    body: InviteCreate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> GenericMessage:
    """Invite a user to the family by email (privacy-preserving)."""
    current_user, _ = membership
    await family_service.invite_user(db, family_id, body.email, current_user)
    return GenericMessage(message="If a user with that email exists, they will receive an invitation.")


@router.get("/invites", response_model=list[InviteResponse], status_code=status.HTTP_200_OK)
async def get_pending_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InviteResponse]:
    """Get all pending invites for the current user."""
    result = await db.execute(
        select(Invite)
        .options(joinedload(Invite.family), joinedload(Invite.inviting_user))
        .where(
            Invite.invited_user_id == current_user.id,
            Invite.status == "pending",
        )
    )
    invites = result.unique().scalars().all()
    return [
        InviteResponse(
            id=inv.id,
            family_id=inv.family_id,
            family_name=inv.family.name,
            invited_by_name=inv.inviting_user.display_name,
            status=inv.status,
            created_at=inv.created_at,
        )
        for inv in invites
    ]


@router.post("/invites/{invite_id}/respond", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def respond_to_invite(
    invite_id: uuid.UUID,
    body: InviteAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenericMessage:
    """Accept or decline a pending invite."""
    invite = await family_service.respond_to_invite(db, invite_id, current_user, body.action)
    action_past = "accepted" if invite.status == "accepted" else "declined"
    return GenericMessage(message=f"Invite {action_past} successfully")


@router.delete("/families/{family_id}/members/{user_id}", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def remove_member(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> GenericMessage:
    """Remove a member from the family (admin only)."""
    current_user, _ = membership
    await family_service.remove_member(db, family_id, user_id, current_user)
    return GenericMessage(message="Member removed successfully")


@router.patch(
    "/families/{family_id}/members/{user_id}", response_model=FamilyMemberResponse, status_code=status.HTTP_200_OK
)
async def change_member_role(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    body: RoleUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> FamilyMemberResponse:
    """Change a family member's role (admin only)."""
    current_user, _ = membership
    member = await family_service.change_role(db, family_id, user_id, body.role, current_user)
    # Eager-load the user relationship for the response
    await db.refresh(member, ["user"])
    return FamilyMemberResponse(
        user_id=member.user_id,
        email=member.user.email,
        display_name=member.user.display_name,
        avatar_url=member.user.avatar_url,
        role=member.role,
        joined_at=member.joined_at,
    )


@router.post("/families/{family_id}/leave", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def leave_family(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    db: AsyncSession = Depends(get_db),
) -> GenericMessage:
    """Leave a family (cannot be used by the owner)."""
    current_user, _ = membership
    await family_service.leave_family(db, family_id, current_user)
    return GenericMessage(message="You have left the family")
