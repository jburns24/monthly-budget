"""Family service: create, retrieve, and manage families with members.

Behind the repository/UnitOfWork seam (design doc Step 6). Family, FamilyMember,
Invite and User were migrated as one unit because this module is the only place
they are used together — porting any one of them alone would have left the
service reading half its rows through repositories and half through a session.

Risk (a): :func:`get_family_with_members` deliberately uses
``uow.families.get_with_members``, never the bare ``get``, because
``app/routers/family.py:_family_to_response`` walks
``family.members[*].user.email``.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.logging import get_logger
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork

# Alias to avoid shadowing by function parameters named 'timezone'
_utc = timezone.utc

logger = get_logger(__name__)


async def create_family(
    uow: UnitOfWork,
    user: User,
    name: str,
    timezone: str = "America/New_York",
) -> Family:
    """Create a new family and add the requesting user as admin.

    Raises HTTPException(409) if the user already belongs to a family.
    """
    if await uow.members.get_any_for_user(user.id) is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a family")

    now = datetime.now(tz=_utc)
    family = Family(
        name=name,
        timezone=timezone,
        created_by=user.id,
        created_at=now,
    )
    uow.families.add(family)
    # Flushed before the membership row is built: family.id is assigned here.
    await uow.flush()

    member = FamilyMember(
        family_id=family.id,
        user_id=user.id,
        role="admin",
        joined_at=now,
    )
    uow.members.add(member)
    await uow.flush()

    logger.info("family_created", family_id=str(family.id), user_id=str(user.id), name=name)
    return family


async def get_family_with_members(
    uow: UnitOfWork,
    family_id: uuid.UUID,
) -> Family:
    """Return a Family with its members and their user records eager-loaded.

    Raises HTTPException(404) if the family does not exist.
    """
    family = await uow.families.get_with_members(family_id)
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    return family


async def invite_user(
    uow: UnitOfWork,
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
    target_user = await uow.users.get_by_email(email)
    if target_user is None:
        logger.info("invite_user_no_match", family_id=str(family_id))
        return

    # Silently return if the user already belongs to any family
    if await uow.members.get_any_for_user(target_user.id) is not None:
        logger.info("invite_user_already_in_family", family_id=str(family_id), user_id=str(target_user.id))
        return

    # Silently return if the user already has a pending invite to this family
    if await uow.invites.get_pending_for(family_id, target_user.id) is not None:
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
    uow.invites.add(invite)
    await uow.flush()

    logger.info(
        "invite_created",
        family_id=str(family_id),
        invited_user_id=str(target_user.id),
        invited_by=str(invited_by_user.id),
    )


async def respond_to_invite(
    uow: UnitOfWork,
    invite_id: uuid.UUID,
    user: User,
    action: str,
) -> Invite:
    """Accept or decline a pending invite.

    Raises HTTPException(404) if the invite is not found, not owned by the user,
    or not in 'pending' status.
    Raises HTTPException(409) if accepting but the user already belongs to a family.
    """
    invite = await uow.invites.get_pending(invite_id, user.id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")

    now = datetime.now(tz=_utc)

    if action == "decline":
        invite.status = "declined"
        invite.responded_at = now
        await uow.flush()
        logger.info("invite_declined", invite_id=str(invite_id), user_id=str(user.id))
        return invite

    # action == "accept"
    # Check user not already in a family
    if await uow.members.get_any_for_user(user.id) is not None:
        raise HTTPException(status_code=409, detail="User already belongs to a family")

    # Add user as member
    member = FamilyMember(
        family_id=invite.family_id,
        user_id=user.id,
        role="member",
        joined_at=now,
    )
    uow.members.add(member)
    invite.status = "accepted"
    invite.responded_at = now
    await uow.flush()

    logger.info("invite_accepted", invite_id=str(invite_id), user_id=str(user.id), family_id=str(invite.family_id))
    return invite


async def _family_and_member(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> tuple[Family, FamilyMember]:
    """Load the family and one of its membership rows, 404ing on either miss.

    The three membership-mutating functions below all open the same way, and the
    order matters to the API contract: a missing family is "Family not found"
    even when the membership is also absent.
    """
    family = await uow.families.get(family_id)
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")

    member = await uow.members.get_for_user_in_family(family_id, target_user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    return family, member


async def remove_member(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requesting_user: User,
) -> None:
    """Remove a member from a family.

    Raises HTTPException(404) if the family or target member is not found.
    Raises HTTPException(403) if attempting to remove the family owner or the last admin.
    """
    family, target_member = await _family_and_member(uow, family_id, target_user_id)

    # Cannot remove the family owner
    if target_user_id == family.created_by:
        raise HTTPException(status_code=403, detail="Cannot remove the family owner")

    # Cannot remove the last admin
    if target_member.role == "admin" and await uow.members.count_admins(family_id) <= 1:
        raise HTTPException(status_code=403, detail="Cannot remove the last admin")

    await uow.members.delete(target_member)
    await uow.flush()

    logger.info(
        "member_removed",
        family_id=str(family_id),
        target_user_id=str(target_user_id),
        removed_by=str(requesting_user.id),
    )


async def change_role(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
    requesting_user: User,
) -> FamilyMember:
    """Change a family member's role.

    Raises HTTPException(404) if the family or target member is not found.
    Raises HTTPException(403) if demoting the family owner or the last admin.
    """
    family, target_member = await _family_and_member(uow, family_id, target_user_id)

    # Check if this is a demotion (admin -> member)
    if target_member.role == "admin" and new_role == "member":
        # Cannot demote the family owner
        if target_user_id == family.created_by:
            raise HTTPException(status_code=403, detail="Cannot demote the family owner")

        # Cannot demote the last admin
        if await uow.members.count_admins(family_id) <= 1:
            raise HTTPException(status_code=403, detail="Cannot demote the last admin")

    target_member.role = new_role
    await uow.flush()

    logger.info(
        "member_role_changed",
        family_id=str(family_id),
        target_user_id=str(target_user_id),
        new_role=new_role,
        changed_by=str(requesting_user.id),
    )
    return target_member


async def leave_family(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    user: User,
) -> None:
    """Allow a user to leave a family.

    Raises HTTPException(404) if the user is not a member of the family.
    Raises HTTPException(403) if the user is the family owner.
    """
    family, member = await _family_and_member(uow, family_id, user.id)

    # Owner cannot leave
    if user.id == family.created_by:
        raise HTTPException(status_code=403, detail="The owner cannot leave the family")

    await uow.members.delete(member)
    await uow.flush()

    logger.info("member_left", family_id=str(family_id), user_id=str(user.id))
