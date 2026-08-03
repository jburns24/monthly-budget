"""In-memory implementation of :class:`~app.ports.repositories.category.CategoryRepository`."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from app.adapters.memory.store import MemoryStore, postgres_tier
from app.models.category import Category


class MemoryCategoryRepository:
    """Category reads and writes over a :class:`~app.adapters.memory.store.MemoryStore`."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def get_in_family(self, category_id: UUID, family_id: UUID) -> Category | None:
        category = self._store.get(Category, category_id)
        if category is None or category.family_id != family_id:
            return None
        return category

    async def list_active(self, family_id: UUID) -> list[Category]:
        return sorted(
            (c for c in self._store.rows(Category) if c.family_id == family_id and c.is_active),
            key=lambda c: (c.sort_order, c.name),
        )

    async def list_names(self, family_id: UUID) -> set[str]:
        return {c.name for c in self._store.rows(Category) if c.family_id == family_id}

    async def first_active(self, family_id: UUID) -> Category | None:
        active = await self.list_active(family_id)
        return active[0] if active else None

    def add(self, category: Category) -> None:
        self._store.add(category)

    def add_all(self, categories: Sequence[Category]) -> None:
        self._store.add_all(categories)

    async def delete(self, category: Category) -> None:
        self._store.delete(category)

    # ------------------------------------------------------------------
    # Postgres tier
    # ------------------------------------------------------------------

    async def find_similar_active(self, family_id: UUID, term: str, threshold: float) -> Category | None:
        postgres_tier("CategoryRepository.find_similar_active", "pg_trgm similarity() scoring and ranking")

    async def most_used_since(self, family_id: UUID, cutoff: date) -> Category | None:
        postgres_tier(
            "CategoryRepository.most_used_since", "a JOIN + GROUP BY ranking whose tie-breaks a fake would guess"
        )
