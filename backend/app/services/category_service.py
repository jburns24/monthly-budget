"""Category service: create, list, and update budget categories.

First aggregate on the repository/UnitOfWork seam. Note what is *absent*: no
``AsyncSession``, no ``select()``, no ``sqlalchemy.exc.IntegrityError``. The 409
paths key on :class:`~app.ports.errors.UniqueViolation`, which the SQLAlchemy
adapter translates ``IntegrityError`` into and the in-memory adapter raises
directly — which is what lets ``tests/unit/test_category_service.py`` exercise
them with no database.
"""

import uuid

from fastapi import HTTPException

from app.logging import get_logger
from app.models.category import Category
from app.ports.errors import UniqueViolation
from app.ports.unit_of_work import UnitOfWork

logger = get_logger(__name__)


async def _flush_or_name_conflict(uow: UnitOfWork, name: str | None) -> None:
    """Flush, turning a duplicate-name rejection into HTTP 409.

    The rollback discards the whole request, not just the failed write. Preserved
    from the pre-seam code; the right fix is a savepoint, and that is a behaviour
    change deserving its own PR (design doc risk (f)).
    """
    try:
        await uow.flush()
    except UniqueViolation:
        await uow.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Category '{name}' already exists in this family",
        )


async def create_category(
    uow: UnitOfWork,
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
    uow.categories.add(category)
    await _flush_or_name_conflict(uow, name)

    logger.info(
        "category_created",
        category_id=str(category.id),
        family_id=str(family_id),
        name=name,
    )
    return category


async def list_active_categories(
    uow: UnitOfWork,
    family_id: uuid.UUID,
) -> list[Category]:
    """Return all active categories for a family, ordered by sort_order ASC then name ASC."""
    return await uow.categories.list_active(family_id)


async def update_category(
    uow: UnitOfWork,
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
    category = await uow.categories.get_in_family(category_id, family_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # No add() call: the repository hands back a tracked instance, so mutating it
    # and flushing is the update. Any adapter returning a copy or a DTO would make
    # this a silent no-op (design doc risk (b)).
    if name is not None:
        category.name = name
    if icon is not None:
        category.icon = icon
    if sort_order is not None:
        category.sort_order = sort_order

    await _flush_or_name_conflict(uow, name)

    logger.info(
        "category_updated",
        category_id=str(category_id),
        family_id=str(family_id),
    )
    return category


async def delete_category(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    category_id: uuid.UUID,
) -> dict:
    """Delete or archive a category.

    - If no expenses reference the category: hard-delete it and return {"deleted": True}.
    - If expenses exist: set is_active=False (archive) and return
      {"deleted": False, "archived": True, "expense_count": N}.

    Raises HTTPException(404) if the category is not found or belongs to a different family.
    """
    category = await uow.categories.get_in_family(category_id, family_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    expense_count = await uow.expenses.count_by_category(category_id)

    if expense_count > 0:
        category.is_active = False
        await uow.flush()
        logger.info(
            "category_archived",
            category_id=str(category_id),
            family_id=str(family_id),
            expense_count=expense_count,
        )
        return {"deleted": False, "archived": True, "expense_count": expense_count}

    await uow.categories.delete(category)
    await uow.flush()
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
    uow: UnitOfWork,
    family_id: uuid.UUID,
) -> int:
    """Bulk-create the 6 default categories for a family.

    Idempotent: skips any category whose name already exists in the family.
    Returns the number of newly created categories.
    """
    existing_names = await uow.categories.list_names(family_id)

    new_categories = [
        Category(family_id=family_id, name=name, icon=icon, sort_order=sort_order, is_active=True)
        for name, icon, sort_order in _DEFAULT_CATEGORIES
        if name not in existing_names
    ]

    if new_categories:
        uow.categories.add_all(new_categories)
        await uow.flush()

    created = len(new_categories)
    logger.info(
        "default_categories_seeded",
        family_id=str(family_id),
        created=created,
        skipped=len(_DEFAULT_CATEGORIES) - created,
    )
    return created
