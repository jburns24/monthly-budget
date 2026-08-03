"""Category suggestion using pg_trgm similarity with a 90-day usage fallback.

Takes a :class:`~app.ports.repositories.category.CategoryRepository` rather than
a ``UnitOfWork``: this module only reads categories, and narrowing to the one
repository it needs is the point of using ``typing.Protocol`` (see
``docs/data-layer-ports-design.md`` section 1).

Both queries below used to exist twice — once here against ``AsyncSession`` and
once behind the port — because the Category port was defined in full while its
only caller, ``receipt_service``, was not migrated until Step 7. Step 7 retired
the local copies; ``_trgm_match`` is now ``CategoryRepository.find_similar_active``
and the 90-day fallback is ``most_used_since``. ``first_active_category`` is gone
entirely: callers use ``uow.categories.first_active`` directly.
"""

import uuid
from datetime import date, timedelta

from app.logging import get_logger
from app.models.category import Category
from app.ports.repositories.category import CategoryRepository

logger = get_logger(__name__)

# pg_trgm similarity floor. Below this, a "match" is noise.
SIMILARITY_THRESHOLD = 0.3

_USAGE_WINDOW = timedelta(days=90)


async def suggest_for_store(
    categories: CategoryRepository,
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

    Both paths are Postgres tier, so the in-memory adapter raises
    ``NotImplementedError`` here rather than approximating trigram scoring.
    """
    for term, source in ((category_hint, "hint"), (store_name, "store_name")):
        if not term:
            continue
        category = await categories.find_similar_active(family_id, term, SIMILARITY_THRESHOLD)
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

    category = await categories.most_used_since(family_id, date.today() - _USAGE_WINDOW)
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
