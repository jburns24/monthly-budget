"""Category service: create, list, and update budget categories."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.category import Category

logger = get_logger(__name__)


async def create_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    name: str,
    icon: str | None,
    sort_order: int = 0,
) -> Category:
    """Create a new category for a family.

    Raises HTTPException(409) if a category with the same name already exists in the family.
    """
    category = Category(
        family_id=family_id,
        name=name,
        icon=icon,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(category)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Category '{name}' already exists in this family",
        )

    logger.info(
        "category_created",
        category_id=str(category.id),
        family_id=str(family_id),
        name=name,
    )
    return category


async def list_active_categories(
    db: AsyncSession,
    family_id: uuid.UUID,
) -> list[Category]:
    """Return all active categories for a family, ordered by sort_order ASC then name ASC."""
    result = await db.execute(
        select(Category)
        .where(Category.family_id == family_id, Category.is_active.is_(True))
        .order_by(Category.sort_order.asc(), Category.name.asc())
    )
    return list(result.scalars().all())


async def update_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str | None,
    icon: str | None,
    sort_order: int | None,
) -> Category:
    """Update an existing category's fields (only non-None fields are applied).

    Raises HTTPException(404) if the category is not found or belongs to a different family.
    Raises HTTPException(409) if the new name conflicts with an existing category in the family.
    """
    result = await db.execute(select(Category).where(Category.id == category_id, Category.family_id == family_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if name is not None:
        category.name = name
    if icon is not None:
        category.icon = icon
    if sort_order is not None:
        category.sort_order = sort_order

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Category '{name}' already exists in this family",
        )

    logger.info(
        "category_updated",
        category_id=str(category_id),
        family_id=str(family_id),
    )
    return category
