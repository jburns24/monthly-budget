"""Unit tests for the Receipt ORM model.

Verifies that the model maps correctly to the database schema, relationships
load, and the CHECK constraint rejects invalid status values.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.expense import Expense  # noqa: F401 — registers with Base.metadata
from app.models.family_member import FamilyMember  # noqa: F401 — registers with Base.metadata
from app.models.invite import Invite  # noqa: F401 — registers with Base.metadata
from app.models.monthly_goal import MonthlyGoal  # noqa: F401 — registers with Base.metadata
from app.models.receipt import Receipt
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from tests.conftest import (
    create_test_category,
    create_test_expense,
    create_test_family,
    create_test_receipt,
    create_test_user,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test NullPool engine and transaction rollback."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_create_and_retrieve_all_fields(db_session: AsyncSession) -> None:
    """Receipt can be created and retrieved with all fields intact."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    receipt_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)

    receipt = Receipt(
        id=receipt_id,
        family_id=family.id,
        uploaded_by=owner.id,
        image_path="/data/receipts/test.jpg",
        raw_response={"is_receipt": True, "confidence": "high"},
        parsed_date=date(2026, 4, 1),
        parsed_total_cents=4523,
        parsed_merchant="Whole Foods",
        status="completed",
        error_message=None,
        created_at=now,
    )
    db_session.add(receipt)
    await db_session.flush()
    await db_session.refresh(receipt)

    fetched = await db_session.get(Receipt, receipt_id)
    assert fetched is not None
    assert fetched.id == receipt_id
    assert fetched.family_id == family.id
    assert fetched.uploaded_by == owner.id
    assert fetched.image_path == "/data/receipts/test.jpg"
    assert fetched.raw_response == {"is_receipt": True, "confidence": "high"}
    assert fetched.parsed_date == date(2026, 4, 1)
    assert fetched.parsed_total_cents == 4523
    assert fetched.parsed_merchant == "Whole Foods"
    assert fetched.status == "completed"
    assert fetched.error_message is None
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_receipt_id_auto_generated(db_session: AsyncSession) -> None:
    """Receipt.id is auto-generated as a UUID when not provided."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    receipt = await create_test_receipt(db_session, family, owner)

    assert receipt.id is not None
    assert isinstance(receipt.id, uuid.UUID)


@pytest.mark.asyncio
async def test_receipt_default_status_is_processing(db_session: AsyncSession) -> None:
    """Receipt.status defaults to 'processing'."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    receipt = await create_test_receipt(db_session, family, owner)

    assert receipt.status == "processing"


@pytest.mark.asyncio
async def test_receipt_check_constraint_rejects_invalid_status(db_session: AsyncSession) -> None:
    """CHECK constraint ck_receipts_status rejects values outside the allowed set."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    now = datetime.now(tz=timezone.utc)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Receipt(
                    family_id=family.id,
                    uploaded_by=owner.id,
                    status="invalid_status",
                    created_at=now,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_receipt_check_constraint_accepts_valid_statuses(db_session: AsyncSession) -> None:
    """CHECK constraint allows all three valid status values."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    for status in ("processing", "completed", "failed"):
        receipt = await create_test_receipt(db_session, family, owner, status=status)
        assert receipt.status == status


@pytest.mark.asyncio
async def test_receipt_family_relationship_loads(db_session: AsyncSession) -> None:
    """Receipt.family relationship resolves to the correct Family."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    receipt = await create_test_receipt(db_session, family, owner)
    await db_session.refresh(receipt, ["family"])

    assert receipt.family is not None
    assert receipt.family.id == family.id


@pytest.mark.asyncio
async def test_receipt_uploader_relationship_loads(db_session: AsyncSession) -> None:
    """Receipt.uploader relationship resolves to the correct User."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    receipt = await create_test_receipt(db_session, family, owner)
    await db_session.refresh(receipt, ["uploader"])

    assert receipt.uploader is not None
    assert receipt.uploader.id == owner.id


@pytest.mark.asyncio
async def test_receipt_expense_relationship_one_to_one(db_session: AsyncSession) -> None:
    """Receipt.expense resolves to the linked Expense (one-to-one via Expense.receipt_id)."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    receipt = await create_test_receipt(db_session, family, owner, status="completed")
    expense = await create_test_expense(db_session, family, owner, category, receipt_id=receipt.id)

    await db_session.refresh(receipt, ["expense"])

    assert receipt.expense is not None
    assert receipt.expense.id == expense.id


@pytest.mark.asyncio
async def test_receipt_nullable_fields_can_be_none(db_session: AsyncSession) -> None:
    """All optional fields can be None."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    receipt = await create_test_receipt(
        db_session,
        family,
        owner,
        image_path=None,
        raw_response=None,
        parsed_date=None,
        parsed_total_cents=None,
        parsed_merchant=None,
        error_message=None,
    )

    assert receipt.image_path is None
    assert receipt.raw_response is None
    assert receipt.parsed_date is None
    assert receipt.parsed_total_cents is None
    assert receipt.parsed_merchant is None
    assert receipt.error_message is None


@pytest.mark.asyncio
async def test_family_receipts_relationship(db_session: AsyncSession) -> None:
    """Family.receipts relationship returns all receipts for the family."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    r1 = await create_test_receipt(db_session, family, owner)
    r2 = await create_test_receipt(db_session, family, owner)

    await db_session.refresh(family, ["receipts"])

    receipt_ids = {r.id for r in family.receipts}
    assert r1.id in receipt_ids
    assert r2.id in receipt_ids


@pytest.mark.asyncio
async def test_user_uploaded_receipts_relationship(db_session: AsyncSession) -> None:
    """User.uploaded_receipts relationship returns all receipts uploaded by the user."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    r1 = await create_test_receipt(db_session, family, owner)
    r2 = await create_test_receipt(db_session, family, owner)

    await db_session.refresh(owner, ["uploaded_receipts"])

    receipt_ids = {r.id for r in owner.uploaded_receipts}
    assert r1.id in receipt_ids
    assert r2.id in receipt_ids


@pytest.mark.asyncio
async def test_expense_receipt_relationship(db_session: AsyncSession) -> None:
    """Expense.receipt resolves to the linked Receipt."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    receipt = await create_test_receipt(db_session, family, owner, status="completed")
    expense = await create_test_expense(db_session, family, owner, category, receipt_id=receipt.id)

    await db_session.refresh(expense, ["receipt"])

    assert expense.receipt is not None
    assert expense.receipt.id == receipt.id


@pytest.mark.asyncio
async def test_expense_receipt_status_property(db_session: AsyncSession) -> None:
    """Expense.receipt_status property returns status of linked receipt."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    receipt = await create_test_receipt(db_session, family, owner, status="completed")
    expense = await create_test_expense(db_session, family, owner, category, receipt_id=receipt.id)

    await db_session.refresh(expense, ["receipt"])

    assert expense.receipt_status == "completed"


@pytest.mark.asyncio
async def test_expense_receipt_status_property_none_when_no_receipt(db_session: AsyncSession) -> None:
    """Expense.receipt_status returns None when no receipt is linked."""
    owner = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)
    category = await create_test_category(db_session, family)

    expense = await create_test_expense(db_session, family, owner, category)
    await db_session.refresh(expense, ["receipt"])

    assert expense.receipt is None
    assert expense.receipt_status is None
