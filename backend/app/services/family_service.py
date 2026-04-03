"""Family service: create and retrieve families with members."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.logging import get_logger
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.user import User

logger = get_logger(__name__)


async def create_family(
    db: AsyncSession,
    user: User,
    name: str,
    timezone: str = "America/New_York",
) -> Family:
    """Create a new family and add the requesting user as admin.

    Raises HTTPException(409) if the user already belongs to a family.
    """
    result = await db.execute(select(FamilyMember).where(FamilyMember.user_id == user.id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a family")

    family = Family(
        name=name,
        timezone=timezone,
        created_by=user.id,
    )
    db.add(family)
    await db.flush()

    member = FamilyMember(
        family_id=family.id,
        user_id=user.id,
        role="admin",
    )
    db.add(member)
    await db.flush()

    logger.info("family_created", family_id=str(family.id), user_id=str(user.id), name=name)
    return family


async def get_family_with_members(
    db: AsyncSession,
    family_id: uuid.UUID,
) -> Family:
    """Return a Family with its members and their user records eager-loaded.

    Raises HTTPException(404) if the family does not exist.
    """
    result = await db.execute(
        select(Family).options(joinedload(Family.members).joinedload(FamilyMember.user)).where(Family.id == family_id)
    )
    family = result.unique().scalar_one_or_none()
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    return family


async def invite_user(
    db: AsyncSession,
    family_id: uuid.UUID,
    email: str,
    invited_by_user: User,
) -> None:
    """Invite a user to a family by email address (privacy-preserving).

    This method never reveals whether the email matched a registered user.
    It silently returns (without creating an invite) in all these cases:
    - The email does not correspond to any registered user
    - The matched user already belongs to a family
    - The matched user already has a pending invite to this family

    Only when a matched user is eligible will an Invite record be created.
    """
    # Look up target user by email — privacy-preserving: silently return if not found
    result = await db.execute(select(User).where(User.email == email))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        logger.info("invite_user_no_match", family_id=str(family_id))
        return

    # Silently return if the user already belongs to any family
    result = await db.execute(select(FamilyMember).where(FamilyMember.user_id == target_user.id))
    existing_membership = result.scalar_one_or_none()
    if existing_membership is not None:
        logger.info("invite_user_already_in_family", family_id=str(family_id), user_id=str(target_user.id))
        return

    # Silently return if the user already has a pending invite to this family
    result = await db.execute(
        select(Invite).where(
            Invite.family_id == family_id,
            Invite.invited_user_id == target_user.id,
            Invite.status == "pending",
        )
    )
    existing_invite = result.scalar_one_or_none()
    if existing_invite is not None:
        logger.info("invite_user_duplicate_invite", family_id=str(family_id), user_id=str(target_user.id))
        return

    # User is eligible — create the invite
    invite = Invite(
        family_id=family_id,
        invited_user_id=target_user.id,
        invited_by=invited_by_user.id,
        status="pending",
    )
    db.add(invite)
    await db.flush()

    logger.info(
        "invite_created",
        family_id=str(family_id),
        invited_user_id=str(target_user.id),
        invited_by=str(invited_by_user.id),
    )
