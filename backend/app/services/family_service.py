"""Family service: create, retrieve, and manage families with members."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.logging import get_logger
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.user import User

# Alias to avoid shadowing by function parameters named 'timezone'
_utc = timezone.utc

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

    now = datetime.now(tz=_utc)
    family = Family(
        name=name,
        timezone=timezone,
        created_by=user.id,
        created_at=now,
    )
    db.add(family)
    await db.flush()

    member = FamilyMember(
        family_id=family.id,
        user_id=user.id,
        role="admin",
        joined_at=now,
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
        created_at=datetime.now(tz=_utc),
    )
    db.add(invite)
    await db.flush()

    logger.info(
        "invite_created",
        family_id=str(family_id),
        invited_user_id=str(target_user.id),
        invited_by=str(invited_by_user.id),
    )


async def respond_to_invite(
    db: AsyncSession,
    invite_id: uuid.UUID,
    user: User,
    action: str,
) -> Invite:
    """Accept or decline a pending invite.

    Raises HTTPException(404) if the invite is not found, not owned by the user,
    or not in 'pending' status.
    Raises HTTPException(409) if accepting but the user already belongs to a family.
    """
    result = await db.execute(
        select(Invite).where(
            Invite.id == invite_id,
            Invite.invited_user_id == user.id,
            Invite.status == "pending",
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")

    now = datetime.now(tz=timezone.utc)

    if action == "decline":
        invite.status = "declined"
        invite.responded_at = now
        await db.flush()
        logger.info("invite_declined", invite_id=str(invite_id), user_id=str(user.id))
        return invite

    # action == "accept"
    # Check user not already in a family
    membership_result = await db.execute(select(FamilyMember).where(FamilyMember.user_id == user.id))
    if membership_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a family")

    # Add user as member
    member = FamilyMember(
        family_id=invite.family_id,
        user_id=user.id,
        role="member",
        joined_at=now,
    )
    db.add(member)
    invite.status = "accepted"
    invite.responded_at = now
    await db.flush()

    logger.info("invite_accepted", invite_id=str(invite_id), user_id=str(user.id), family_id=str(invite.family_id))
    return invite


async def remove_member(
    db: AsyncSession,
    family_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requesting_user: User,
) -> None:
    """Remove a member from a family.

    Raises HTTPException(404) if the family or target member is not found.
    Raises HTTPException(403) if attempting to remove the family owner or the last admin.
    """
    # Get the family
    family_result = await db.execute(select(Family).where(Family.id == family_id))
    family = family_result.scalar_one_or_none()
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    # Get the target member
    member_result = await db.execute(
        select(FamilyMember).where(FamilyMember.family_id == family_id, FamilyMember.user_id == target_user_id)
    )
    target_member = member_result.scalar_one_or_none()
    if target_member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Cannot remove the family owner
    if target_user_id == family.created_by:
        raise HTTPException(status_code=403, detail="Cannot remove the family owner")

    # Cannot remove the last admin
    if target_member.role == "admin":
        admin_count_result = await db.execute(
            select(func.count())
            .select_from(FamilyMember)
            .where(FamilyMember.family_id == family_id, FamilyMember.role == "admin")
        )
        admin_count = admin_count_result.scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=403, detail="Cannot remove the last admin")

    await db.delete(target_member)
    await db.flush()

    logger.info(
        "member_removed",
        family_id=str(family_id),
        target_user_id=str(target_user_id),
        removed_by=str(requesting_user.id),
    )


async def change_role(
    db: AsyncSession,
    family_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
    requesting_user: User,
) -> FamilyMember:
    """Change a family member's role.

    Raises HTTPException(404) if the family or target member is not found.
    Raises HTTPException(403) if demoting the family owner or the last admin.
    """
    # Get the family
    family_result = await db.execute(select(Family).where(Family.id == family_id))
    family = family_result.scalar_one_or_none()
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    # Get the target member
    member_result = await db.execute(
        select(FamilyMember).where(FamilyMember.family_id == family_id, FamilyMember.user_id == target_user_id)
    )
    target_member = member_result.scalar_one_or_none()
    if target_member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Check if this is a demotion (admin -> member)
    is_demotion = target_member.role == "admin" and new_role == "member"

    if is_demotion:
        # Cannot demote the family owner
        if target_user_id == family.created_by:
            raise HTTPException(status_code=403, detail="Cannot demote the family owner")

        # Cannot demote the last admin
        admin_count_result = await db.execute(
            select(func.count())
            .select_from(FamilyMember)
            .where(FamilyMember.family_id == family_id, FamilyMember.role == "admin")
        )
        admin_count = admin_count_result.scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=403, detail="Cannot demote the last admin")

    target_member.role = new_role
    await db.flush()

    logger.info(
        "member_role_changed",
        family_id=str(family_id),
        target_user_id=str(target_user_id),
        new_role=new_role,
        changed_by=str(requesting_user.id),
    )
    return target_member


async def leave_family(
    db: AsyncSession,
    family_id: uuid.UUID,
    user: User,
) -> None:
    """Allow a user to leave a family.

    Raises HTTPException(404) if the user is not a member of the family.
    Raises HTTPException(403) if the user is the family owner.
    """
    # Get the family (need to check ownership)
    family_result = await db.execute(select(Family).where(Family.id == family_id))
    family = family_result.scalar_one_or_none()
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    # Get the member record
    member_result = await db.execute(
        select(FamilyMember).where(FamilyMember.family_id == family_id, FamilyMember.user_id == user.id)
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Owner cannot leave
    if user.id == family.created_by:
        raise HTTPException(status_code=403, detail="The owner cannot leave the family")

    await db.delete(member)
    await db.flush()

    logger.info("member_left", family_id=str(family_id), user_id=str(user.id))
