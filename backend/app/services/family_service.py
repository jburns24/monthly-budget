"""Family service: create and retrieve families with members."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.logging import get_logger
from app.models.family import Family
from app.models.family_member import FamilyMember
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
