"""Category service: create, list, and update budget categories."""

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.category import Category
from app.models.expense import Expense

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


async def _count_category_expenses(db: AsyncSession, category_id: uuid.UUID) -> int:
    """Return the number of expenses that reference this category."""
    result = await db.execute(select(func.count()).select_from(Expense).where(Expense.category_id == category_id))
    return result.scalar_one()


async def delete_category(
    db: AsyncSession,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> dict:
    """Delete or archive a category.

    - If no expenses reference the category: hard-delete it and return {"deleted": True}.
    - If expenses exist: set is_active=False (archive) and return
      {"deleted": False, "archived": True, "expense_count": N}.

    Raises HTTPException(404) if the category is not found or belongs to a different family.
    """
    result = await db.execute(select(Category).where(Category.id == category_id, Category.family_id == family_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    expense_count = await _count_category_expenses(db, category_id)

    if expense_count > 0:
        category.is_active = False
        await db.flush()
        logger.info(
            "category_archived",
            category_id=str(category_id),
            family_id=str(family_id),
            expense_count=expense_count,
        )
        return {"deleted": False, "archived": True, "expense_count": expense_count}

    await db.delete(category)
    await db.flush()
    logger.info(
        "category_deleted",
        category_id=str(category_id),
        family_id=str(family_id),
    )
    return {"deleted": True}


_DEFAULT_CATEGORIES: list[tuple[str, str, int]] = [
    ("Groceries", "\U0001f6d2", 0),  # 🛒
    ("Dining", "\U0001f374", 1),  # 🍴
    ("Transport", "\U0001f697", 2),  # 🚗
    ("Entertainment", "\U0001f3a5", 3),  # 🎥
    ("Bills", "\U0001f9fe", 4),  # 🧾
    ("Other", "\U0001f4c1", 5),  # 📁
]


async def seed_default_categories(
    db: AsyncSession,
    family_id: uuid.UUID,
) -> int:
    """Bulk-create the 6 default categories for a family.

    Idempotent: skips any category whose name already exists in the family.
    Returns the number of newly created categories.
    """
    existing_result = await db.execute(select(Category.name).where(Category.family_id == family_id))
    existing_names: set[str] = set(existing_result.scalars().all())

    created = 0
    for name, icon, sort_order in _DEFAULT_CATEGORIES:
        if name in existing_names:
            continue
        db.add(Category(family_id=family_id, name=name, icon=icon, sort_order=sort_order, is_active=True))
        created += 1

    if created:
        await db.flush()

    logger.info(
        "default_categories_seeded",
        family_id=str(family_id),
        created=created,
        skipped=len(_DEFAULT_CATEGORIES) - created,
    )
    return created
