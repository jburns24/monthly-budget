"""User router: profile endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.schemas.family import FamilyBrief
from app.schemas.user import UserResponse, UserUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return the authenticated user's profile, including family membership if any."""
    family_brief: FamilyBrief | None = None
    result = await db.execute(select(FamilyMember).where(FamilyMember.user_id == current_user.id))
    membership = result.scalar_one_or_none()
    if membership is not None:
        await db.refresh(membership, ["family"])
        family_brief = FamilyBrief(
            id=membership.family_id,
            name=membership.family.name,
            role=membership.role,
        )

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        timezone=current_user.timezone,
        family=family_brief,
    )


@router.put("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Update the authenticated user's profile fields."""
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.timezone is not None:
        current_user.timezone = body.timezone

    logger.info("user_profile_updated", user_id=str(current_user.id))
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        timezone=current_user.timezone,
    )
