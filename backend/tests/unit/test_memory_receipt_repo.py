"""Unit tests for the in-memory ReceiptRepository. No database.

Focus: ``list_filtered``'s status/uploaded_by/date_from/date_to filters, and
pinning the NULL-exclusion semantic — a date_from/date_to bound must not let a
still-processing or failed receipt through, because SQL comparisons against
NULL are never true and the fake has to mirror that rather than "helpfully"
including unparsed rows.
"""

import uuid
from datetime import date, datetime, timezone

import pytest

from tests.unit.conftest import make_receipt, seed


def _dated(receipt, when: datetime):
    """Pin ``created_at`` explicitly.

    The store fills ``created_at`` from its ``server_default`` shim at flush
    time, so several receipts seeded together in one ``seed()`` call can land
    with identical timestamps. Ordering assertions need distinct, known values.
    """
    receipt.created_at = when
    return receipt


def _parsed(receipt, when: date):
    """Set ``parsed_date`` — ``make_receipt`` has no parameter for it."""
    receipt.parsed_date = when
    return receipt


# ---------------------------------------------------------------------------
# get_in_family
# ---------------------------------------------------------------------------


async def test_get_in_family_returns_the_receipt(uow, family_id) -> None:
    receipt = make_receipt(family_id, uuid.uuid4())
    await seed(uow, receipt)

    found = await uow.receipts.get_in_family(receipt.id, family_id)

    assert found is not None
    assert found.id == receipt.id


async def test_get_in_family_returns_none_for_another_familys_receipt(uow, family_id) -> None:
    receipt = make_receipt(family_id, uuid.uuid4())
    await seed(uow, receipt)

    assert await uow.receipts.get_in_family(receipt.id, uuid.uuid4()) is None


async def test_get_in_family_returns_none_for_an_unknown_id(uow, family_id) -> None:
    assert await uow.receipts.get_in_family(uuid.uuid4(), family_id) is None


# ---------------------------------------------------------------------------
# list_filtered — ordering, family scoping, paging
# ---------------------------------------------------------------------------


async def test_list_filtered_orders_newest_created_at_first(uow, family_id) -> None:
    user_id = uuid.uuid4()
    early = _dated(make_receipt(family_id, user_id), datetime(2026, 1, 1, tzinfo=timezone.utc))
    late = _dated(make_receipt(family_id, user_id), datetime(2026, 3, 1, tzinfo=timezone.utc))
    await seed(uow, early, late)

    results = await uow.receipts.list_filtered(family_id, None, None, None, None, 50, 0)

    assert [r.id for r in results] == [late.id, early.id]


async def test_list_filtered_is_scoped_to_the_family(uow, family_id) -> None:
    other_family = uuid.uuid4()
    mine = make_receipt(family_id, uuid.uuid4())
    theirs = make_receipt(other_family, uuid.uuid4())
    await seed(uow, mine, theirs)

    results = await uow.receipts.list_filtered(family_id, None, None, None, None, 50, 0)

    assert [r.id for r in results] == [mine.id]


async def test_list_filtered_paginates_with_limit_and_offset(uow, family_id) -> None:
    user_id = uuid.uuid4()
    receipts = [
        _dated(make_receipt(family_id, user_id), datetime(2026, 1, i, tzinfo=timezone.utc)) for i in range(1, 6)
    ]
    await seed(uow, *receipts)

    page = await uow.receipts.list_filtered(family_id, None, None, None, None, 2, 2)

    # Newest-first order is [day5, day4, day3, day2, day1]; offset 2, limit 2 -> [day3, day2].
    assert [r.id for r in page] == [receipts[2].id, receipts[1].id]


# ---------------------------------------------------------------------------
# list_filtered — status / uploaded_by filters
# ---------------------------------------------------------------------------


async def test_list_filtered_filters_by_status(uow, family_id) -> None:
    user_id = uuid.uuid4()
    completed = make_receipt(family_id, user_id, status="completed")
    failed = make_receipt(family_id, user_id, status="failed")
    await seed(uow, completed, failed)

    results = await uow.receipts.list_filtered(family_id, "failed", None, None, None, 50, 0)

    assert [r.id for r in results] == [failed.id]


async def test_list_filtered_filters_by_uploaded_by(uow, family_id) -> None:
    alice, bob = uuid.uuid4(), uuid.uuid4()
    mine = make_receipt(family_id, alice)
    theirs = make_receipt(family_id, bob)
    await seed(uow, mine, theirs)

    results = await uow.receipts.list_filtered(family_id, None, alice, None, None, 50, 0)

    assert [r.id for r in results] == [mine.id]


# ---------------------------------------------------------------------------
# list_filtered — date_from / date_to filters
# ---------------------------------------------------------------------------


async def test_list_filtered_filters_by_date_from(uow, family_id) -> None:
    user_id = uuid.uuid4()
    early = _parsed(make_receipt(family_id, user_id), date(2026, 3, 1))
    late = _parsed(make_receipt(family_id, user_id), date(2026, 4, 15))
    await seed(uow, early, late)

    results = await uow.receipts.list_filtered(family_id, None, None, date(2026, 4, 1), None, 50, 0)

    assert [r.id for r in results] == [late.id]


async def test_list_filtered_filters_by_date_to(uow, family_id) -> None:
    user_id = uuid.uuid4()
    early = _parsed(make_receipt(family_id, user_id), date(2026, 3, 1))
    late = _parsed(make_receipt(family_id, user_id), date(2026, 4, 15))
    await seed(uow, early, late)

    results = await uow.receipts.list_filtered(family_id, None, None, None, date(2026, 3, 15), 50, 0)

    assert [r.id for r in results] == [early.id]


async def test_list_filtered_combines_status_and_date_range(uow, family_id) -> None:
    user_id = uuid.uuid4()
    in_range_completed = _parsed(make_receipt(family_id, user_id, status="completed"), date(2026, 4, 10))
    in_range_failed = _parsed(make_receipt(family_id, user_id, status="failed"), date(2026, 4, 12))
    out_of_range_completed = _parsed(make_receipt(family_id, user_id, status="completed"), date(2026, 1, 1))
    await seed(uow, in_range_completed, in_range_failed, out_of_range_completed)

    results = await uow.receipts.list_filtered(family_id, "completed", None, date(2026, 4, 1), date(2026, 4, 30), 50, 0)

    assert [r.id for r in results] == [in_range_completed.id]


# ---------------------------------------------------------------------------
# list_filtered — the NULL-exclusion semantic
# ---------------------------------------------------------------------------


async def test_date_filter_excludes_receipts_with_no_parsed_date(uow, family_id) -> None:
    """SQL comparisons against NULL are never true: a still-processing or failed
    receipt has ``parsed_date is None`` and must not satisfy any date_from/date_to
    bound, no matter how wide. A fake that let NULL rows through here would pass
    every other ``list_filtered`` test in this file while silently breaking the
    real endpoint's date-range filter.
    """
    user_id = uuid.uuid4()
    unparsed = make_receipt(family_id, user_id, status="processing")
    assert unparsed.parsed_date is None
    await seed(uow, unparsed)

    results = await uow.receipts.list_filtered(family_id, None, None, date(2000, 1, 1), date(2100, 1, 1), 50, 0)

    assert results == []


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


async def test_get_status_returns_the_persisted_status(uow, family_id) -> None:
    receipt = make_receipt(family_id, uuid.uuid4(), status="processing")
    await seed(uow, receipt)

    assert await uow.receipts.get_status(receipt.id) == "processing"


async def test_get_status_returns_none_for_an_unknown_id(uow) -> None:
    assert await uow.receipts.get_status(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# add / delete
# ---------------------------------------------------------------------------


async def test_add_is_invisible_until_flush(uow, family_id) -> None:
    """The real session runs with autoflush=False; the fake mirrors that."""
    receipt = make_receipt(family_id, uuid.uuid4())

    uow.receipts.add(receipt)
    assert await uow.receipts.list_filtered(family_id, None, None, None, None, 50, 0) == []

    await uow.flush()

    results = await uow.receipts.list_filtered(family_id, None, None, None, None, 50, 0)
    assert [r.id for r in results] == [receipt.id]


async def test_flush_assigns_id_and_created_at(uow, family_id) -> None:
    """Postgres supplies id (Python default) and created_at (server_default); the fake must too."""
    receipt = make_receipt(family_id, uuid.uuid4())
    assert receipt.id is None
    assert receipt.created_at is None

    uow.receipts.add(receipt)
    await uow.flush()

    assert isinstance(receipt.id, uuid.UUID)
    assert isinstance(receipt.created_at, datetime)


async def test_delete_removes_the_row_on_flush(uow, family_id) -> None:
    receipt = make_receipt(family_id, uuid.uuid4())
    await seed(uow, receipt)

    await uow.receipts.delete(receipt)
    assert await uow.receipts.get_in_family(receipt.id, family_id) is not None

    await uow.flush()

    assert await uow.receipts.get_in_family(receipt.id, family_id) is None


# ---------------------------------------------------------------------------
# Postgres-tier: no fake for claim_for_retry
# ---------------------------------------------------------------------------


async def test_claim_for_retry_refuses_to_be_faked(uow) -> None:
    """Row-lock serialization of the conditional UPDATE is Postgres tier; the
    fake says so instead of letting a single-threaded call trivially "win"
    without ever exercising the concurrency guarantee that is the entire point.
    """
    with pytest.raises(NotImplementedError, match="Postgres") as exc_info:
        await uow.receipts.claim_for_retry(uuid.uuid4())

    assert "row-lock serialization" in str(exc_info.value)
    assert "concurrency" in str(exc_info.value)
