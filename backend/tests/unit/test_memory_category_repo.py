"""Unit tests for the in-memory CategoryRepository. No database."""

import uuid
from datetime import datetime

import pytest

from app.ports.errors import UniqueViolation
from tests.unit.conftest import make_category, seed


async def test_flush_assigns_id_and_created_at(uow, family_id) -> None:
    """Postgres supplies id (Python default) and created_at (server_default); the fake must too."""
    category = make_category(family_id, "Groceries")
    assert category.id is None

    uow.categories.add(category)
    await uow.flush()

    assert isinstance(category.id, uuid.UUID)
    assert isinstance(category.created_at, datetime)


async def test_flush_does_not_overwrite_explicit_values(uow, family_id) -> None:
    """Defaults fill gaps only; a caller-supplied id survives."""
    chosen = uuid.uuid4()
    category = make_category(family_id, "Groceries")
    category.id = chosen

    uow.categories.add(category)
    await uow.flush()

    assert category.id == chosen


async def test_queries_do_not_see_unflushed_writes(uow, family_id) -> None:
    """The real session runs with autoflush=False, so a staged add is invisible until flush."""
    uow.categories.add(make_category(family_id, "Pending"))

    assert await uow.categories.list_names(family_id) == set()

    await uow.flush()

    assert await uow.categories.list_names(family_id) == {"Pending"}


async def test_duplicate_name_in_the_same_family_raises_unique_violation(uow, family_id) -> None:
    """The fake enforces uq_categories_family_name and names it in the error."""
    await seed(uow, make_category(family_id, "Groceries"))
    uow.categories.add(make_category(family_id, "Groceries"))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_categories_family_name"


async def test_same_name_in_a_different_family_is_allowed(uow, family_id) -> None:
    """The constraint is composite, not on name alone."""
    other_family = uuid.uuid4()
    await seed(uow, make_category(family_id, "Groceries"))

    uow.categories.add(make_category(other_family, "Groceries"))
    await uow.flush()

    assert await uow.categories.list_names(other_family) == {"Groceries"}


async def test_renaming_onto_an_existing_name_raises_unique_violation(uow, family_id) -> None:
    """An *update* that collides must fail too, not just an insert."""
    existing = make_category(family_id, "Existing")
    target = make_category(family_id, "Target")
    await seed(uow, existing, target)

    target.name = "Existing"

    with pytest.raises(UniqueViolation):
        await uow.flush()


async def test_mutating_a_returned_instance_is_tracked_without_an_explicit_add(uow, family_id) -> None:
    """Services rely on implicit dirty tracking: ``category.name = x; await flush()``."""
    await seed(uow, make_category(family_id, "Before"))
    (fetched,) = await uow.categories.list_active(family_id)

    fetched.name = "After"
    await uow.flush()

    assert await uow.categories.list_names(family_id) == {"After"}


async def test_get_in_family_returns_the_category(uow, family_id) -> None:
    """get_in_family finds a category owned by the family."""
    category = make_category(family_id, "Dining")
    await seed(uow, category)

    found = await uow.categories.get_in_family(category.id, family_id)

    assert found is not None
    assert found.name == "Dining"


async def test_get_in_family_returns_none_for_another_familys_category(uow, family_id) -> None:
    """get_in_family scopes by family_id."""
    category = make_category(family_id, "Private")
    await seed(uow, category)

    assert await uow.categories.get_in_family(category.id, uuid.uuid4()) is None


async def test_get_in_family_returns_none_for_an_unknown_id(uow, family_id) -> None:
    """A missing id is None, not an error."""
    assert await uow.categories.get_in_family(uuid.uuid4(), family_id) is None


async def test_list_active_excludes_archived_and_sorts_by_sort_order_then_name(uow, family_id) -> None:
    """list_active mirrors the SQL ORDER BY (sort_order, name)."""
    await seed(
        uow,
        make_category(family_id, "Zebra", sort_order=1),
        make_category(family_id, "Apple", sort_order=2),
        make_category(family_id, "Mango", sort_order=1),
        make_category(family_id, "Archived", sort_order=0, is_active=False),
    )

    names = [c.name for c in await uow.categories.list_active(family_id)]

    assert names == ["Mango", "Zebra", "Apple"]


async def test_list_active_ignores_other_families(uow, family_id) -> None:
    """list_active is family-scoped."""
    await seed(uow, make_category(family_id, "Mine"), make_category(uuid.uuid4(), "Theirs"))

    assert [c.name for c in await uow.categories.list_active(family_id)] == ["Mine"]


async def test_list_names_includes_archived_categories(uow, family_id) -> None:
    """Seeding idempotency depends on archived names being reported."""
    await seed(uow, make_category(family_id, "Active"), make_category(family_id, "Archived", is_active=False))

    assert await uow.categories.list_names(family_id) == {"Active", "Archived"}


async def test_first_active_returns_the_lowest_sorted_active_category(uow, family_id) -> None:
    """first_active picks by (sort_order, name) and skips archived rows."""
    await seed(
        uow,
        make_category(family_id, "Later", sort_order=5),
        make_category(family_id, "Earliest", sort_order=1),
        make_category(family_id, "Archived", sort_order=0, is_active=False),
    )

    first = await uow.categories.first_active(family_id)

    assert first is not None
    assert first.name == "Earliest"


async def test_first_active_returns_none_without_active_categories(uow, family_id) -> None:
    """first_active returns None rather than raising on an empty family."""
    assert await uow.categories.first_active(family_id) is None


async def test_delete_removes_the_row_on_flush(uow, family_id) -> None:
    """delete is staged, then applied by flush."""
    category = make_category(family_id, "Gone")
    await seed(uow, category)

    await uow.categories.delete(category)
    assert await uow.categories.list_names(family_id) == {"Gone"}

    await uow.flush()

    assert await uow.categories.list_names(family_id) == set()


async def test_delete_then_reinsert_the_same_name_in_one_flush(uow, family_id) -> None:
    """Deletes are applied before inserts, so freeing a unique key works in one flush."""
    category = make_category(family_id, "Recycled")
    await seed(uow, category)

    await uow.categories.delete(category)
    uow.categories.add(make_category(family_id, "Recycled", sort_order=9))
    await uow.flush()

    (survivor,) = await uow.categories.list_active(family_id)
    assert survivor.sort_order == 9


# ---------------------------------------------------------------------------
# Postgres-tier methods have no fake
# ---------------------------------------------------------------------------


async def test_find_similar_active_refuses_to_be_faked(uow, family_id) -> None:
    """pg_trgm similarity is Postgres tier; the fake says so instead of guessing."""
    with pytest.raises(NotImplementedError, match="Postgres"):
        await uow.categories.find_similar_active(family_id, "Grocery", 0.3)


async def test_most_used_since_refuses_to_be_faked(uow, family_id) -> None:
    """The ranking query is Postgres tier; the fake says so instead of guessing."""
    from datetime import date

    with pytest.raises(NotImplementedError, match="Postgres"):
        await uow.categories.most_used_since(family_id, date(2026, 1, 1))
