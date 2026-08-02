"""Repository protocol for the Category aggregate."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol
from uuid import UUID

from app.models.category import Category


class CategoryRepository(Protocol):
    """Reads and writes for :class:`~app.models.category.Category`.

    ``typing.Protocol``, not an ABC: structural typing keeps the in-memory
    adapter from importing the SQLAlchemy one, and lets a service narrow to just
    the methods it uses. Conformance is checked statically by
    ``app.adapters.conformance`` (and, because mypy is not yet wired into CI,
    also at runtime by ``tests/unit/test_conformance.py``).

    Do not add ``@runtime_checkable``: it only compares method *names*, which
    would give false confidence rather than none.
    """

    async def get_in_family(self, category_id: UUID, family_id: UUID) -> Category | None:
        """Return the category if it exists *and* belongs to ``family_id``, else None."""
        ...

    async def list_active(self, family_id: UUID) -> list[Category]:
        """Return the family's active categories ordered by ``(sort_order, name)``."""
        ...

    async def list_names(self, family_id: UUID) -> set[str]:
        """Return every category name in the family, archived ones included.

        Backs the idempotency check in seeding, which must not re-create a name
        that exists only as an archived row — the unique constraint covers both.
        """
        ...

    async def first_active(self, family_id: UUID) -> Category | None:
        """Return the lowest-sorted active category, or None if there are none."""
        ...

    def add(self, category: Category) -> None:
        """Stage a new category. Not durable until ``UnitOfWork.flush``."""
        ...

    def add_all(self, categories: Sequence[Category]) -> None:
        """Stage a batch of new categories."""
        ...

    async def delete(self, category: Category) -> None:
        """Stage a hard delete. Not applied until ``UnitOfWork.flush``."""
        ...

    # ------------------------------------------------------------------
    # Postgres tier: no in-memory implementation, integration tests only.
    #
    # These lean on capabilities a fake cannot honestly reproduce, so the memory
    # adapter raises NotImplementedError rather than approximating them.
    # ------------------------------------------------------------------

    async def find_similar_active(self, family_id: UUID, term: str, threshold: float) -> Category | None:
        """Best active category whose name trigram-matches ``term`` above ``threshold``.

        Postgres tier: pg_trgm ``similarity()``. Re-implementing trigram scoring
        in Python would test the re-implementation, not the query.
        """
        ...

    async def most_used_since(self, family_id: UUID, cutoff: date) -> Category | None:
        """Active category with the most expenses on or after ``cutoff``.

        Postgres tier: JOIN + GROUP BY + ``count() DESC LIMIT 1``. A ranking
        query whose tie-breaking a fake would silently get wrong.
        """
        ...
