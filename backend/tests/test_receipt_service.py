"""Tests for receipt_service.process_upload (three-phase transaction).

Covers:
- Pre-phase: MIME validation and sanitize failures → 422
- Phase 1: storage save failure → 500
- Phase 2: Claude API error → 503, receipt marked failed, image deleted
- Phase 2: non-receipt → 422, receipt marked failed, image deleted
- Phase 3: happy path (high confidence + category) → receipt+expense, needs_edit=False
- Phase 3: low confidence → needs_edit=True, expense persists with amount_cents=0
- Phase 3: no suggestion match → falls back to any active category
- Phase 3: family has no active categories → 409, receipt failed, image kept
- Phase 3: no total amount → needs_edit=True
- Helper unit tests: _parse_expense_date, _amount_cents
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.family import Family  # noqa: F401
from app.models.family_member import FamilyMember  # noqa: F401
from app.models.invite import Invite  # noqa: F401
from app.models.monthly_goal import MonthlyGoal  # noqa: F401
from app.models.receipt import Receipt
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401
from app.models.user import User  # noqa: F401
from app.schemas.receipt import ExtractedReceipt
from app.services.receipt_service import _amount_cents, _parse_expense_date, process_upload
from tests.conftest import create_test_category, create_test_family, create_test_user

# ---------------------------------------------------------------------------
# DB fixture (NullPool avoids event-loop conflicts between tests)
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_BYTES = b"\xff\xd8\xff" + b"\x00" * 50  # Not a real JPEG; mocks handle validation


def _fake_path(family_id: uuid.UUID) -> Path:
    return Path(f"/tmp/receipts/{family_id}/test.jpg")


def _extracted(**overrides) -> ExtractedReceipt:
    defaults: dict = dict(
        is_receipt=True,
        confidence="high",
        total_amount=42.50,
        date="2026-03-21",
        store_name="Test Market",
    )
    defaults.update(overrides)
    return ExtractedReceipt(**defaults)


# ---------------------------------------------------------------------------
# Pre-phase: MIME validation failure → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_mime_raises_415(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    with patch(
        "app.services.receipt_service.receipt_storage.validate_mime",
        side_effect=ValueError("Unsupported MIME type"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 415
    assert "Unsupported MIME type" in exc_info.value.detail


@pytest.mark.asyncio
async def test_corrupt_image_raises_400(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            side_effect=Exception("Corrupt image data"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 400
    assert "Invalid image" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Phase 1: storage save failure → 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase1_save_failure_raises_500(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    delete_mock = AsyncMock()

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch(
            "app.services.receipt_service.receipt_storage.save",
            AsyncMock(side_effect=OSError("disk full")),
        ),
        patch("app.services.receipt_service.receipt_storage.delete", delete_mock),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 500
    # image_path was never set (save raised before path was returned), so no delete
    delete_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 2: Claude API error → 503, receipt marked failed, image deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase2_claude_error_raises_503_and_marks_receipt_failed(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_path = _fake_path(family.id)
    delete_mock = AsyncMock()

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", delete_mock),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(side_effect=Exception("Claude API unavailable")),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 503
    # Image is preserved (not deleted) on Claude errors so retry can re-run extraction.
    delete_mock.assert_not_called()

    result = await db_session.execute(select(Receipt).where(Receipt.family_id == family.id))
    receipt = result.scalar_one_or_none()
    assert receipt is not None
    assert receipt.status == "failed"
    assert "Claude API error" in receipt.error_message


# ---------------------------------------------------------------------------
# Phase 2: non-receipt → 422, receipt marked failed, image deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase2_non_receipt_raises_422_and_marks_receipt_failed(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_path = _fake_path(family.id)
    delete_mock = AsyncMock()

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", delete_mock),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=ExtractedReceipt(is_receipt=False, confidence="high")),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 422
    assert "doesn't appear to be a receipt" in exc_info.value.detail
    delete_mock.assert_called_once_with(image_path)

    result = await db_session.execute(select(Receipt).where(Receipt.family_id == family.id))
    receipt = result.scalar_one_or_none()
    assert receipt is not None
    assert receipt.status == "failed"


# ---------------------------------------------------------------------------
# Phase 3: happy path — high confidence + category → expense created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_high_confidence_creates_expense(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")
    image_path = _fake_path(family.id)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted()),
        ),
        patch(
            "app.services.receipt_service.category_suggestion.suggest_for_store",
            AsyncMock(return_value=category),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert receipt.status == "completed"
    assert receipt.parsed_merchant == "Test Market"
    assert receipt.parsed_total_cents == 4250
    assert receipt.parsed_date == date(2026, 3, 21)
    assert expense is not None
    assert expense.amount_cents == 4250
    assert expense.category_id == category.id
    assert expense.description == "Test Market"
    assert expense.family_id == family.id
    assert needs_edit is False


# ---------------------------------------------------------------------------
# Phase 3: low confidence → needs_edit=True, expense with placeholder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_low_confidence_needs_edit_true(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_path = _fake_path(family.id)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted(confidence="low", total_amount=None, date=None, store_name=None)),
        ),
        patch(
            "app.services.receipt_service.category_suggestion.suggest_for_store",
            AsyncMock(return_value=category),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert receipt.status == "completed"
    assert needs_edit is True
    assert expense is not None
    # Spec §Unit 3: low-confidence → amount_cents=0 (Needs-review chip key).
    assert expense.amount_cents == 0


@pytest.mark.asyncio
async def test_low_confidence_with_valid_total_still_persists_amount_zero(
    db_session: AsyncSession,
) -> None:
    """Even when Claude returned a total, low-confidence forces amount_cents=0.

    Regression: previous code wrote ``total_cents`` (e.g. 4250) when confidence
    was ``low`` but a total was parsed, suppressing the "Needs review" chip.
    Spec §Unit 3 requires the placeholder 0 so the user reviews before saving.
    """
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_path = _fake_path(family.id)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted(confidence="low", total_amount=42.50)),
        ),
        patch(
            "app.services.receipt_service.category_suggestion.suggest_for_store",
            AsyncMock(return_value=category),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert receipt.status == "completed"
    # Parsed total is still captured on the receipt row for later review UI.
    assert receipt.parsed_total_cents == 4250
    assert needs_edit is True
    assert expense is not None
    assert expense.amount_cents == 0


# ---------------------------------------------------------------------------
# Phase 3: no suggestion match → falls back to any active category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_suggestion_falls_back_to_first_active_category(db_session: AsyncSession) -> None:
    """When suggest_for_store finds nothing, the expense still gets created.

    Regression: previously the expense was silently skipped, so the upload
    returned 201 with nothing in the family's expense list.
    """
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")
    image_path = _fake_path(family.id)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted()),
        ),
        patch(
            "app.services.receipt_service.category_suggestion.suggest_for_store",
            AsyncMock(return_value=None),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert receipt.status == "completed"
    assert expense is not None
    assert expense.category_id == category.id
    assert needs_edit is False


@pytest.mark.asyncio
async def test_low_confidence_no_store_name_still_creates_expense(db_session: AsyncSession) -> None:
    """A low-confidence extraction with no store name still produces an expense.

    Regression: ``suggest_for_store(family, "")`` never matches on similarity, and
    a family with no expenses in the last 90 days has no usage fallback either —
    which used to mean the receipt completed with no expense at all.
    """
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")
    image_path = _fake_path(family.id)

    extracted = _extracted(confidence="low", total_amount=None, date=None, store_name=None)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=extracted),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert receipt.status == "completed"
    assert expense is not None
    assert expense.category_id == category.id
    assert expense.amount_cents == 0
    assert expense.description == "Unknown merchant"
    assert needs_edit is True


# ---------------------------------------------------------------------------
# Phase 3: family has no active categories → 409, receipt failed, image kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_categories_raises_409(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_path = _fake_path(family.id)
    delete_mock = AsyncMock()

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", delete_mock),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted()),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert exc_info.value.status_code == 409
    assert "categor" in str(exc_info.value.detail).lower()
    # Image is preserved so the retry endpoint works once a category exists.
    delete_mock.assert_not_called()

    result = await db_session.execute(select(Receipt).where(Receipt.family_id == family.id))
    receipt = result.scalar_one()
    assert receipt.status == "failed"
    assert receipt.error_message is not None


# ---------------------------------------------------------------------------
# Phase 3: no total amount → needs_edit=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_no_total_needs_edit_true(db_session: AsyncSession) -> None:
    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_path = _fake_path(family.id)

    with (
        patch("app.services.receipt_service.receipt_storage.validate_mime"),
        patch(
            "app.services.receipt_service.receipt_storage.sanitize_image",
            return_value=(b"sanitized", (100, 100)),
        ),
        patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
        patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
        patch(
            "app.services.receipt_service.claude_client.extract_receipt",
            AsyncMock(return_value=_extracted(total_amount=None)),
        ),
        patch(
            "app.services.receipt_service.category_suggestion.suggest_for_store",
            AsyncMock(return_value=category),
        ),
    ):
        receipt, expense, needs_edit = await process_upload(db_session, MagicMock(), family.id, user.id, FAKE_BYTES)

    assert needs_edit is True
    assert expense is not None
    # needs_edit=True when total_cents is None → amount_cents=0 placeholder.
    assert expense.amount_cents == 0


# ---------------------------------------------------------------------------
# Helper unit tests: _parse_expense_date
# ---------------------------------------------------------------------------


def test_parse_expense_date_valid_iso() -> None:
    assert _parse_expense_date("2026-03-21") == date(2026, 3, 21)


def test_parse_expense_date_none_returns_today() -> None:
    assert _parse_expense_date(None) == date.today()


def test_parse_expense_date_invalid_string_returns_today() -> None:
    assert _parse_expense_date("not-a-date") == date.today()


def test_parse_expense_date_partial_string_returns_today() -> None:
    assert _parse_expense_date("2026-03") == date.today()


# ---------------------------------------------------------------------------
# Helper unit tests: _amount_cents
# ---------------------------------------------------------------------------


def test_amount_cents_converts_dollars_to_cents() -> None:
    assert _amount_cents(42.50) == 4250


def test_amount_cents_rounds_fractional_cents() -> None:
    result = _amount_cents(1.005)
    assert result is not None
    assert result >= 100


def test_amount_cents_none_returns_none() -> None:
    assert _amount_cents(None) is None


def test_amount_cents_zero_returns_none() -> None:
    assert _amount_cents(0.0) is None


def test_amount_cents_negative_returns_none() -> None:
    assert _amount_cents(-10.0) is None


def test_amount_cents_tiny_positive_returns_minimum_1() -> None:
    assert _amount_cents(0.001) == 1
