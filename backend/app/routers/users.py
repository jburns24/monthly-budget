"""User router: profile endpoints."""

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_user
from app.logging import get_logger
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        timezone=current_user.timezone,
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
