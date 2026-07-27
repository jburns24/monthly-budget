"""Category suggestion service using pg_trgm similarity with 90-day usage fallback."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.category import Category
from app.models.expense import Expense

logger = get_logger(__name__)


async def _trgm_match(db: AsyncSession, family_id: uuid.UUID, term: str) -> Category | None:
    """Best active category whose name trigram-matches ``term`` above 0.3, else None."""
    if not term:
        return None
    result = await db.execute(
        select(Category)
        .where(
            Category.family_id == family_id,
            Category.is_active.is_(True),
            func.similarity(Category.name, term) > 0.3,
        )
        .order_by(func.similarity(Category.name, term).desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def suggest_for_store(
    db: AsyncSession,
    family_id: uuid.UUID,
    store_name: str,
    category_hint: str | None = None,
) -> Category | None:
    """Suggest an active category for a store name.

    Tries pg_trgm similarity > 0.3 against ``category_hint`` first, then against
    ``store_name``, then falls back to the most-used active category from expenses
    in the last 90 days. Returns None if nothing matches.

    The hint is checked first because it is the far stronger signal: it is a
    category label (e.g. "Groceries") produced by the receipt extractor, and a
    store name like "Safeway" will never trigram-match a category named
    "Groceries" no matter how well the extraction went. ``store_name`` is still
    tried second, since families do sometimes name a category after a merchant.
    """
    for term, source in ((category_hint, "hint"), (store_name, "store_name")):
        if not term:
            continue
        category = await _trgm_match(db, family_id, term)
        if category is not None:
            logger.info(
                "category_suggestion_trgm_match",
                family_id=str(family_id),
                store_name=store_name,
                matched_term=term,
                matched_on=source,
                category_id=str(category.id),
                category_name=category.name,
            )
            return category

    cutoff = date.today() - timedelta(days=90)
    fallback_result = await db.execute(
        select(Category)
        .join(Expense, Expense.category_id == Category.id)
        .where(
            Expense.family_id == family_id,
            Category.is_active.is_(True),
            Expense.expense_date >= cutoff,
        )
        .group_by(Category.id)
        .order_by(func.count().desc())
        .limit(1)
    )
    category = fallback_result.scalar_one_or_none()
    if category is not None:
        logger.info(
            "category_suggestion_fallback",
            family_id=str(family_id),
            store_name=store_name,
            category_id=str(category.id),
            category_name=category.name,
        )
    else:
        logger.info(
            "category_suggestion_none",
            family_id=str(family_id),
            store_name=store_name,
        )
    return category


async def first_active_category(db: AsyncSession, family_id: uuid.UUID) -> Category | None:
    """Return the family's first active category, ordered by ``(sort_order, name)``.

    Last-resort fallback for callers that must have *some* category to attach a
    row to. :func:`suggest_for_store` deliberately returns ``None`` when neither
    the name-similarity nor the 90-day usage path matches — that is the right
    answer for "which category best fits this store?", but a receipt upload
    still has to produce an Expense, so it degrades to this instead of silently
    creating nothing. Returns ``None`` only when the family has no active
    categories at all.
    """
    result = await db.execute(
        select(Category)
        .where(Category.family_id == family_id, Category.is_active.is_(True))
        .order_by(Category.sort_order, Category.name)
        .limit(1)
    )
    return result.scalar_one_or_none()
