"""User router: profile endpoints."""

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_user
from app.deps.provider import get_uow
from app.logging import get_logger
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork
from app.schemas.family import FamilyBrief
from app.schemas.user import UserResponse, UserUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_me(
    current_user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
) -> UserResponse:
    """Return the authenticated user's profile, including family membership if any."""
    family_brief: FamilyBrief | None = None
    membership = await uow.members.get_with_family(current_user.id)
    if membership is not None:
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
    uow: UnitOfWork = Depends(get_uow),
) -> UserResponse:
    """Update the authenticated user's profile fields.

    Persists explicitly via ``uow.users.add`` + ``uow.flush`` rather than
    relying on the session identity map plus ``get_db``'s teardown commit —
    see docs/data-layer-ports-design.md risk (b).
    """
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.timezone is not None:
        current_user.timezone = body.timezone

    uow.users.add(current_user)
    await uow.flush()

    logger.info("user_profile_updated", user_id=str(current_user.id))
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        timezone=current_user.timezone,
    )
