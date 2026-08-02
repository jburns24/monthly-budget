"""Unit tests for the in-memory UnitOfWork's transaction semantics. No database."""

import uuid

import pytest

from app.ports.errors import StaleObject
from tests.unit.conftest import make_category, make_expense, seed


async def test_rollback_discards_everything_since_the_last_commit(uow, family_id) -> None:
    """rollback() restores the store to the last committed snapshot."""
    await seed(uow, make_category(family_id, "Committed"))
    uow.categories.add(make_category(family_id, "Doomed"))
    await uow.flush()

    await uow.rollback()

    assert await uow.categories.list_names(family_id) == {"Committed"}


async def test_rollback_undoes_updates_not_only_inserts(uow, family_id) -> None:
    """A mutation flushed but not committed is reverted to the committed value."""
    await seed(uow, make_category(family_id, "Original"))
    (fetched,) = await uow.categories.list_active(family_id)
    fetched.name = "Renamed"
    await uow.flush()

    await uow.rollback()

    assert await uow.categories.list_names(family_id) == {"Original"}


async def test_rollback_makes_instances_it_handed_out_unusable(uow, family_id) -> None:
    """Reading an attribute after a rollback raises StaleObject.

    Deliberately stricter than SQLAlchemy, and it stands in for the real bug: a
    rollback expires the instance's attributes, and the next read blows up with
    MissingGreenlet somewhere far away from the rollback that caused it.
    """
    await seed(uow, make_category(family_id, "Original"))
    (fetched,) = await uow.categories.list_active(family_id)

    await uow.rollback()

    with pytest.raises(StaleObject):
        _ = fetched.name


async def test_a_refetch_after_rollback_is_usable(uow, family_id) -> None:
    """Staleness is per-instance: re-reading through the repository works."""
    await seed(uow, make_category(family_id, "Original"))
    (stale,) = await uow.categories.list_active(family_id)
    await uow.rollback()

    (fresh,) = await uow.categories.list_active(family_id)

    assert fresh.name == "Original"
    assert fresh is not stale


async def test_rollback_discards_a_staged_but_unflushed_add(uow, family_id) -> None:
    """Nothing survives a rollback, flushed or not."""
    uow.categories.add(make_category(family_id, "Never"))

    await uow.rollback()
    await uow.flush()

    assert await uow.categories.list_names(family_id) == set()


async def test_commit_makes_the_rollback_point_move_forward(uow, family_id) -> None:
    """After a second commit, rollback restores to that commit, not the first."""
    await seed(uow, make_category(family_id, "First"))
    uow.categories.add(make_category(family_id, "Second"))
    await uow.flush()
    await uow.commit()

    await uow.rollback()

    assert await uow.categories.list_names(family_id) == {"First", "Second"}


# ---------------------------------------------------------------------------
# Savepoints
# ---------------------------------------------------------------------------


async def test_savepoint_rollback_keeps_writes_made_before_it(uow, family_id) -> None:
    """An explicit savepoint rollback is narrower than a full rollback."""
    await seed(uow, make_category(family_id, "Committed"))
    uow.categories.add(make_category(family_id, "BeforeSavepoint"))
    await uow.flush()

    async with uow.savepoint() as savepoint:
        uow.categories.add(make_category(family_id, "InsideSavepoint"))
        await uow.flush()
        await savepoint.rollback()

    assert await uow.categories.list_names(family_id) == {"Committed", "BeforeSavepoint"}


async def test_savepoint_rolls_back_on_exception_and_re_raises(uow, family_id) -> None:
    """The block's exception propagates; its writes do not."""
    await seed(uow, make_category(family_id, "Committed"))

    with pytest.raises(RuntimeError, match="boom"):
        async with uow.savepoint():
            uow.categories.add(make_category(family_id, "Discarded"))
            await uow.flush()
            raise RuntimeError("boom")

    assert await uow.categories.list_names(family_id) == {"Committed"}


async def test_savepoint_keeps_its_writes_on_a_clean_exit(uow, family_id) -> None:
    """Leaving the block without error releases the savepoint, keeping the writes."""
    async with uow.savepoint():
        uow.categories.add(make_category(family_id, "Kept"))
        await uow.flush()

    assert await uow.categories.list_names(family_id) == {"Kept"}


async def test_nested_savepoints_unwind_independently(uow, family_id) -> None:
    """An inner savepoint rollback does not touch the outer one's writes."""
    async with uow.savepoint():
        uow.categories.add(make_category(family_id, "Outer"))
        await uow.flush()
        async with uow.savepoint() as inner:
            uow.categories.add(make_category(family_id, "Inner"))
            await uow.flush()
            await inner.rollback()

    assert await uow.categories.list_names(family_id) == {"Outer"}


async def test_full_rollback_inside_a_savepoint_discards_the_savepoint_too(uow, family_id) -> None:
    """A full rollback clears the savepoint stack — the outer transaction is gone."""
    await seed(uow, make_category(family_id, "Committed"))

    async with uow.savepoint():
        uow.categories.add(make_category(family_id, "Doomed"))
        await uow.flush()
        await uow.rollback()

    assert await uow.categories.list_names(family_id) == {"Committed"}


# ---------------------------------------------------------------------------
# ExpenseRepository
# ---------------------------------------------------------------------------


async def test_count_by_category_counts_flushed_expenses(uow, family_id) -> None:
    """count_by_category backs the archive-vs-hard-delete decision."""
    category = make_category(family_id, "Counted")
    await seed(uow, category)
    await seed(uow, *(make_expense(family_id, category.id) for _ in range(3)))

    assert await uow.expenses.count_by_category(category.id) == 3


async def test_count_by_category_returns_zero_for_an_unused_category(uow) -> None:
    """An unreferenced category counts zero, not None."""
    assert await uow.expenses.count_by_category(uuid.uuid4()) == 0
