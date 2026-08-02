"""Family router: family CRUD, invite management, and member management endpoints."""

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_user, require_family_admin, require_family_member
from app.deps.provider import get_uow
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork
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
    uow: UnitOfWork = Depends(get_uow),
) -> FamilyResponse:
    """Create a new family with the current user as admin owner."""
    family = await family_service.create_family(uow, current_user, body.name, body.timezone)
    # Re-fetch with members eager-loaded for response
    family = await family_service.get_family_with_members(uow, family.id)
    logger.info("family_created_endpoint", family_id=str(family.id), user_id=str(current_user.id))
    return _family_to_response(family)


@router.get("/families/{family_id}", response_model=FamilyResponse, status_code=status.HTTP_200_OK)
async def get_family(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> FamilyResponse:
    """Get family details with all members."""
    family = await family_service.get_family_with_members(uow, family_id)
    return _family_to_response(family)


@router.post("/families/{family_id}/invites", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def invite_to_family(
    family_id: uuid.UUID,
    body: InviteCreate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> GenericMessage:
    """Invite a user to the family by email (privacy-preserving)."""
    current_user, _ = membership
    await family_service.invite_user(uow, family_id, body.email, current_user)
    return GenericMessage(message="If a user with that email exists, they will receive an invitation.")


@router.get("/invites", response_model=list[InviteResponse], status_code=status.HTTP_200_OK)
async def get_pending_invites(
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> list[InviteResponse]:
    """Get all pending invites for the current user."""
    invites = await uow.invites.list_pending_for_user_detailed(current_user.id)
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
    uow: UnitOfWork = Depends(get_uow),
) -> GenericMessage:
    """Accept or decline a pending invite."""
    invite = await family_service.respond_to_invite(uow, invite_id, current_user, body.action)
    action_past = "accepted" if invite.status == "accepted" else "declined"
    return GenericMessage(message=f"Invite {action_past} successfully")


@router.delete("/families/{family_id}/members/{user_id}", response_model=GenericMessage, status_code=status.HTTP_200_OK)
async def remove_member(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> GenericMessage:
    """Remove a member from the family (admin only)."""
    current_user, _ = membership
    await family_service.remove_member(uow, family_id, user_id, current_user)
    return GenericMessage(message="Member removed successfully")


@router.patch(
    "/families/{family_id}/members/{user_id}", response_model=FamilyMemberResponse, status_code=status.HTTP_200_OK
)
async def change_member_role(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    body: RoleUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    uow: UnitOfWork = Depends(get_uow),
) -> FamilyMemberResponse:
    """Change a family member's role (admin only)."""
    current_user, _ = membership
    await family_service.change_role(uow, family_id, user_id, body.role, current_user)
    # Re-fetch with the user relationship eager-loaded for the response.
    member = await uow.members.get_with_user(family_id, user_id)
    assert member is not None  # change_role above already proved this row exists
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
    uow: UnitOfWork = Depends(get_uow),
) -> GenericMessage:
    """Leave a family (cannot be used by the owner)."""
    current_user, _ = membership
    await family_service.leave_family(uow, family_id, current_user)
    return GenericMessage(message="You have left the family")
