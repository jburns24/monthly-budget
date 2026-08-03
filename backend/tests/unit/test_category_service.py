"""Unit tests for category_service against the in-memory adapter. No database.

The equivalent Postgres-tier coverage lives in ``tests/test_categories_service.py``
and ``tests/test_categories_api.py``. These tests exist to prove the seam: the
same service code, the same HTTP 409 on a duplicate name, with no connection.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.schemas.category import CategoryResponse
from app.services.category_service import (
    _DEFAULT_CATEGORIES,
    create_category,
    delete_category,
    list_active_categories,
    seed_default_categories,
    update_category,
)
from tests.unit.conftest import make_category, make_expense, seed

# ---------------------------------------------------------------------------
# create_category
# ---------------------------------------------------------------------------


async def test_create_category_returns_a_populated_category(uow, family_id) -> None:
    """create_category fills in every field the response schema needs."""
    category = await create_category(uow, family_id, name="Dining", icon="fork", sort_order=3)

    assert category.family_id == family_id
    assert category.name == "Dining"
    assert category.icon == "fork"
    assert category.sort_order == 3
    assert category.is_active is True
    assert isinstance(category.id, uuid.UUID)
    assert category.created_at is not None


async def test_created_category_validates_as_a_response(uow, family_id) -> None:
    """CategoryResponse requires id and created_at, so the fake must supply both."""
    category = await create_category(uow, family_id, name="Bills", icon=None, sort_order=0)

    response = CategoryResponse.model_validate(category)

    assert response.name == "Bills"
    assert response.created_at == category.created_at


async def test_create_category_rejects_a_duplicate_name_with_409(uow, family_id) -> None:
    """The unique constraint translation is what drives the 409 — no database needed."""
    await seed(uow, make_category(family_id, "Groceries"))

    with pytest.raises(HTTPException) as exc_info:
        await create_category(uow, family_id, name="Groceries", icon=None)

    assert exc_info.value.status_code == 409
    assert "Groceries" in exc_info.value.detail


async def test_create_category_rolls_the_request_back_on_a_duplicate(uow, family_id) -> None:
    """The 409 path discards the whole transaction, as the SQLAlchemy version does."""
    await seed(uow, make_category(family_id, "Groceries"))

    with pytest.raises(HTTPException):
        await create_category(uow, family_id, name="Groceries", icon=None)

    assert await uow.categories.list_names(family_id) == {"Groceries"}


async def test_create_category_allows_the_same_name_in_another_family(uow, family_id) -> None:
    """The constraint is (family_id, name)."""
    other_family = uuid.uuid4()
    await create_category(uow, family_id, name="Transport", icon=None)

    other = await create_category(uow, other_family, name="Transport", icon=None)

    assert other.family_id == other_family


# ---------------------------------------------------------------------------
# list_active_categories
# ---------------------------------------------------------------------------


async def test_list_active_categories_excludes_archived_and_sorts(uow, family_id) -> None:
    """Ordering is (sort_order, name); archived rows are hidden."""
    await seed(
        uow,
        make_category(family_id, "Zebra", sort_order=1),
        make_category(family_id, "Apple", sort_order=2),
        make_category(family_id, "Mango", sort_order=1),
        make_category(family_id, "Hidden", is_active=False),
    )

    names = [c.name for c in await list_active_categories(uow, family_id)]

    assert names == ["Mango", "Zebra", "Apple"]


async def test_list_active_categories_is_empty_for_a_new_family(uow, family_id) -> None:
    """No categories means an empty list, not None."""
    assert await list_active_categories(uow, family_id) == []


# ---------------------------------------------------------------------------
# update_category
# ---------------------------------------------------------------------------


async def test_update_category_applies_only_the_fields_given(uow, family_id) -> None:
    """None means "leave alone", which is why the fake must hand back a live instance."""
    category = make_category(family_id, "Old Name", sort_order=5)
    category.icon = "star"
    await seed(uow, category)

    updated = await update_category(uow, family_id, category.id, name="New Name", icon=None, sort_order=None)

    assert updated.name == "New Name"
    assert updated.icon == "star"
    assert updated.sort_order == 5


async def test_update_category_persists_the_change(uow, family_id) -> None:
    """The mutation must reach the store, not just the returned object."""
    category = make_category(family_id, "Before")
    await seed(uow, category)

    await update_category(uow, family_id, category.id, name="After", icon=None, sort_order=None)

    assert await uow.categories.list_names(family_id) == {"After"}


async def test_update_category_raises_404_for_an_unknown_id(uow, family_id) -> None:
    """A missing category is a 404, not a crash."""
    with pytest.raises(HTTPException) as exc_info:
        await update_category(uow, family_id, uuid.uuid4(), name="X", icon=None, sort_order=None)

    assert exc_info.value.status_code == 404


async def test_update_category_raises_404_for_another_familys_category(uow, family_id) -> None:
    """Cross-family updates are indistinguishable from "not found"."""
    category = make_category(family_id, "Protected")
    await seed(uow, category)

    with pytest.raises(HTTPException) as exc_info:
        await update_category(uow, uuid.uuid4(), category.id, name="Hacked", icon=None, sort_order=None)

    assert exc_info.value.status_code == 404


async def test_update_category_raises_409_on_a_name_collision(uow, family_id) -> None:
    """Renaming onto a sibling's name is a 409, driven by the same translated error."""
    target = make_category(family_id, "Target")
    await seed(uow, make_category(family_id, "Existing"), target)

    with pytest.raises(HTTPException) as exc_info:
        await update_category(uow, family_id, target.id, name="Existing", icon=None, sort_order=None)

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# delete_category
# ---------------------------------------------------------------------------


async def test_delete_category_hard_deletes_an_unused_category(uow, family_id) -> None:
    """No expenses reference it, so the row goes."""
    category = make_category(family_id, "ToDelete")
    await seed(uow, category)
    category_id = category.id

    result = await delete_category(uow, family_id, category_id)

    assert result == {"deleted": True}
    assert await uow.categories.get_in_family(category_id, family_id) is None


async def test_delete_category_archives_a_category_with_expenses(uow, family_id) -> None:
    """Referenced categories are archived so historical expenses keep their label."""
    category = make_category(family_id, "WithExpenses")
    await seed(uow, category)
    await seed(uow, make_expense(family_id, category.id))

    result = await delete_category(uow, family_id, category.id)

    assert result == {"deleted": False, "archived": True, "expense_count": 1}
    survivor = await uow.categories.get_in_family(category.id, family_id)
    assert survivor is not None
    assert survivor.is_active is False


async def test_delete_category_raises_404_for_an_unknown_id(uow, family_id) -> None:
    """A missing category is a 404."""
    with pytest.raises(HTTPException) as exc_info:
        await delete_category(uow, family_id, uuid.uuid4())

    assert exc_info.value.status_code == 404


async def test_delete_category_raises_404_for_another_familys_category(uow, family_id) -> None:
    """Cross-family deletes are refused as "not found"."""
    category = make_category(family_id, "Protected")
    await seed(uow, category)

    with pytest.raises(HTTPException) as exc_info:
        await delete_category(uow, uuid.uuid4(), category.id)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# seed_default_categories
# ---------------------------------------------------------------------------


async def test_seed_default_categories_creates_the_full_set(uow, family_id) -> None:
    """A new family gets every default, with the declared icons and sort order."""
    created = await seed_default_categories(uow, family_id)

    assert created == len(_DEFAULT_CATEGORIES)
    by_name = {c.name: c for c in await uow.categories.list_active(family_id)}
    for name, icon, sort_order in _DEFAULT_CATEGORIES:
        assert by_name[name].icon == icon
        assert by_name[name].sort_order == sort_order


async def test_seed_default_categories_is_idempotent(uow, family_id) -> None:
    """Seeding twice must not raise on the unique constraint or duplicate rows."""
    first = await seed_default_categories(uow, family_id)
    second = await seed_default_categories(uow, family_id)

    assert (first, second) == (len(_DEFAULT_CATEGORIES), 0)
    assert len(await uow.categories.list_active(family_id)) == len(_DEFAULT_CATEGORIES)


async def test_seed_default_categories_skips_names_that_already_exist(uow, family_id) -> None:
    """A pre-existing default name is left alone and not counted."""
    await seed(uow, make_category(family_id, "Groceries"))

    created = await seed_default_categories(uow, family_id)

    assert created == len(_DEFAULT_CATEGORIES) - 1


async def test_seed_default_categories_skips_archived_names(uow, family_id) -> None:
    """The unique constraint covers archived rows, so seeding must too."""
    await seed(uow, make_category(family_id, "Groceries", is_active=False))

    created = await seed_default_categories(uow, family_id)

    assert created == len(_DEFAULT_CATEGORIES) - 1
