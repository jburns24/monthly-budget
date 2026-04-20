"""API endpoint tests for all receipt router endpoints.

Tests cover every receipt router endpoint using the authenticated_client fixture
with a NullPool database session override for per-test transaction rollback.

Endpoints tested:
  POST   /api/families/{family_id}/receipts                         — upload (201/413/415/429)
  GET    /api/families/{family_id}/receipts                         — list
  GET    /api/families/{family_id}/receipts/{receipt_id}            — get one
  GET    /api/families/{family_id}/receipts/{receipt_id}/image      — stream image (410)
  POST   /api/families/{family_id}/receipts/{receipt_id}/retry      — retry (409)
  DELETE /api/families/{family_id}/receipts/{receipt_id}            — delete (204/403)

Claude mock scenarios tested: success, medium_confidence, low_confidence,
non_receipt, api_error.
"""

import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.dependencies import get_anthropic_client
from app.models.family import Family  # noqa: F401
from app.models.family_member import FamilyMember
from app.models.invite import Invite  # noqa: F401
from app.models.monthly_goal import MonthlyGoal  # noqa: F401
from app.models.receipt import Receipt  # noqa: F401
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401
from app.models.user import User  # noqa: F401
from app.schemas.receipt import ExtractedReceipt
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_category,
    create_test_family,
    create_test_receipt,
    create_test_user,
)

# ---------------------------------------------------------------------------
# DB fixture (NullPool, per-test transaction rollback)
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
# Autouse fixtures (apply to all tests in this module)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    """Ensure decode_token uses the test JWT secret."""
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


@pytest.fixture(autouse=True)
def mock_anthropic():
    """Override the get_anthropic_client dependency so no real Anthropic client is needed."""
    from app.main import app

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    app.dependency_overrides[get_anthropic_client] = lambda: mock_client
    yield mock_client
    app.dependency_overrides.pop(get_anthropic_client, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def override_get_db(session: AsyncSession):
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


def _make_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (50, 50), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


VALID_JPEG = _make_jpeg_bytes()


def _extracted(**overrides: Any) -> ExtractedReceipt:
    return ExtractedReceipt(
        is_receipt=overrides.get("is_receipt", True),
        confidence=overrides.get("confidence", "high"),
        total_amount=overrides.get("total_amount", 42.50),
        date=overrides.get("date", "2026-03-21"),
        store_name=overrides.get("store_name", "Test Market"),
    )


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/receipts — 5 Claude scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_success_returns_201(db_session: AsyncSession, authenticated_client, tmp_path: Path) -> None:
    """Happy path: 201 with receipt + expense, needs_edit=False."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")
    image_path = tmp_path / "test.jpg"

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
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
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    body = resp.json()
    assert body["receipt"]["status"] == "completed"
    assert body["receipt"]["parsed_merchant"] == "Test Market"
    assert body["receipt"]["parsed_total_cents"] == 4250
    assert body["expense_id"] is not None
    assert body["needs_edit"] is False


@pytest.mark.asyncio
async def test_upload_low_confidence_returns_201_needs_edit(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    """Low confidence: 201 with needs_edit=True."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_path = tmp_path / "test.jpg"

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
            patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
            patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(return_value=_extracted(confidence="low", total_amount=None, store_name=None, date=None)),
            ),
            patch(
                "app.services.receipt_service.category_suggestion.suggest_for_store",
                AsyncMock(return_value=category),
            ),
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    assert resp.json()["needs_edit"] is True


@pytest.mark.asyncio
async def test_upload_medium_confidence_returns_201(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    """Medium confidence with total: 201, needs_edit=False."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_path = tmp_path / "test.jpg"

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
            patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
            patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(return_value=_extracted(confidence="medium", date=None)),
            ),
            patch(
                "app.services.receipt_service.category_suggestion.suggest_for_store",
                AsyncMock(return_value=category),
            ),
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    assert resp.json()["needs_edit"] is False


@pytest.mark.asyncio
async def test_upload_non_receipt_returns_422(db_session: AsyncSession, authenticated_client, tmp_path: Path) -> None:
    """Non-receipt image returns 422."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_path = tmp_path / "test.jpg"

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
            patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
            patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(return_value=ExtractedReceipt(is_receipt=False, confidence="high")),
            ),
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422
    assert "doesn't appear to be a receipt" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_claude_api_error_returns_503(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    """Claude API failure returns 503."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_path = tmp_path / "test.jpg"

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
            patch("app.services.receipt_service.receipt_storage.save", AsyncMock(return_value=image_path)),
            patch("app.services.receipt_service.receipt_storage.delete", AsyncMock()),
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(side_effect=Exception("API timeout")),
            ),
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_failed_receipt_image_cleaned_up(db_session: AsyncSession, authenticated_client, tmp_path: Path) -> None:
    """Regression (task 26): on a Claude API 503, the Receipt audit row must persist
    with ``status='failed'`` even though the router's ``get_db`` dependency calls
    ``session.rollback()`` when the HTTPException propagates.

    Uses an ``override_get_db`` that faithfully mirrors the production
    ``app.database.get_db`` try/yield/commit/rollback contract so the rollback is
    exercised. The fix in ``_mark_failed`` explicitly commits the failed audit
    row before the HTTPException is raised, so a post-commit rollback becomes
    a no-op and the row survives.

    Also verifies the image is preserved on Claude errors (not deleted) so the
    retry endpoint can re-run extraction against the on-disk file.
    """
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    # Persist setup rows so the separate API session can see them.
    await db_session.commit()

    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"sanitized image bytes")
    delete_mock = AsyncMock()

    # Build an override_get_db that faithfully matches production semantics:
    # yield a session, commit on success, rollback on exception, always close.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    real_session_factory = AsyncSession

    def production_like_get_db(eng):
        async def _override() -> AsyncGenerator[AsyncSession, None]:
            session = real_session_factory(eng, expire_on_commit=False)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        return _override

    app.dependency_overrides[get_db] = production_like_get_db(engine)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
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
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 503

    # Claude errors keep the image on disk so retry can re-run extraction.
    delete_mock.assert_not_called()

    # The audit row must persist even though get_db rolled back on the exception.
    # Open a fresh session to bypass any identity-map caching on db_session.
    verify_session = AsyncSession(engine, expire_on_commit=False)
    try:
        result = await verify_session.execute(select(Receipt).where(Receipt.family_id == family.id))
        receipt = result.scalar_one_or_none()
        assert receipt is not None, "Receipt audit row must persist after 503 (task 26 regression)"
        assert receipt.status == "failed"
        assert receipt.error_message is not None
        assert "Claude API error" in receipt.error_message

        # Clean up the persisted receipt so the per-test rollback strategy isn't
        # left with an orphaned row visible to subsequent tests.
        await verify_session.delete(receipt)
        await verify_session.commit()
    finally:
        await verify_session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Error mapping: 413, 415, 429
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_oversized_file_returns_413(db_session: AsyncSession, authenticated_client) -> None:
    """File larger than 5MB returns 413."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    oversized = b"x" * (5 * 1024 * 1024 + 1)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch(
            "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
            AsyncMock(return_value=(True, 1)),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("big.jpg", oversized, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_invalid_mime_returns_415(db_session: AsyncSession, authenticated_client) -> None:
    """Non-image bytes return 415."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch(
                "app.services.receipt_service.receipt_storage.validate_mime",
                side_effect=ValueError("Unsupported MIME type: 'text/plain'"),
            ),
            patch(
                "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
                AsyncMock(return_value=(True, 1)),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("doc.pdf", b"%PDF-1.4 content", "application/pdf")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_rate_limited_returns_429(db_session: AsyncSession, authenticated_client) -> None:
    """Exceeding daily upload limit returns 429 with Retry-After header."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with patch(
            "app.routers.receipts.rate_limiter.check_and_increment_receipt_upload",
            AsyncMock(return_value=(False, 51)),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(
                    f"/api/families/{family.id}/receipts",
                    files={"file": ("receipt.jpg", VALID_JPEG, "image/jpeg")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "86400"


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_receipts_returns_family_receipts(db_session: AsyncSession, authenticated_client) -> None:
    """GET list returns all receipts for the family."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    await create_test_receipt(db_session, family, user, status="completed")
    await create_test_receipt(db_session, family, user, status="failed")

    other_user = await create_test_user(db_session)
    other_family, _ = await create_test_family(db_session, other_user)
    await create_test_receipt(db_session, other_family, other_user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(r["family_id"] == str(family.id) for r in body)


@pytest.mark.asyncio
async def test_list_receipts_filter_by_status(db_session: AsyncSession, authenticated_client) -> None:
    """GET list with ?status=completed returns only completed receipts."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    await create_test_receipt(db_session, family, user, status="completed")
    await create_test_receipt(db_session, family, user, status="failed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts?status=completed")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts/{receipt_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_returns_200(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    receipt = await create_test_receipt(db_session, family, user, status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts/{receipt.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["id"] == str(receipt.id)


@pytest.mark.asyncio
async def test_get_receipt_returns_404_for_missing(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/families/{family_id}/receipts/{receipt_id}/image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_image_streams_bytes(db_session: AsyncSession, authenticated_client, tmp_path: Path) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_file = tmp_path / "receipt.jpg"
    image_file.write_bytes(VALID_JPEG)
    receipt = await create_test_receipt(db_session, family, user, image_path=str(image_file), status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts/{receipt.id}/image")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == VALID_JPEG


@pytest.mark.asyncio
async def test_get_receipt_image_returns_410_when_missing(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    receipt = await create_test_receipt(db_session, family, user, image_path=None, status="failed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.get(f"/api/families/{family.id}/receipts/{receipt.id}/image")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 410


# ---------------------------------------------------------------------------
# POST /api/families/{family_id}/receipts/{receipt_id}/retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_completed_receipt_returns_409(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    receipt = await create_test_receipt(db_session, family, user, status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(f"/api/families/{family.id}/receipts/{receipt.id}/retry")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_retry_failed_receipt_returns_200(db_session: AsyncSession, authenticated_client, tmp_path: Path) -> None:
    """Retry a failed receipt with image on disk re-runs extraction and returns 200."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_file = tmp_path / "receipt.jpg"
    image_file.write_bytes(VALID_JPEG)
    receipt = await create_test_receipt(db_session, family, user, image_path=str(image_file), status="failed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(return_value=_extracted()),
            ),
            patch(
                "app.services.receipt_service.category_suggestion.suggest_for_store",
                AsyncMock(return_value=category),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(f"/api/families/{family.id}/receipts/{receipt.id}/retry")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["receipt"]["status"] == "completed"
    assert body["expense_id"] is not None


@pytest.mark.asyncio
async def test_retry_processing_receipt_returns_409(db_session: AsyncSession, authenticated_client) -> None:
    """Retrying a receipt already in 'processing' status (e.g. another retry
    in-flight) must return 409 — only 'failed' rows may be retried. Regression
    test for FIX-REVIEW-30 / spec Open Question #2 (optimistic-lock).
    """
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    receipt = await create_test_receipt(db_session, family, user, status="processing")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.post(f"/api/families/{family.id}/receipts/{receipt.id}/retry")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409
    assert "processing" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_uses_atomic_failed_to_processing_update(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    """The retry endpoint must claim the row via an atomic
    ``UPDATE ... WHERE status='failed'`` (optimistic lock). Verify the
    row has already transitioned to 'processing' by the time
    ``reprocess_receipt`` is invoked — proving the claim ran first.
    """
    from app.main import app
    from app.services import receipt_service as _rs

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)
    image_file = tmp_path / "receipt.jpg"
    image_file.write_bytes(VALID_JPEG)
    # Commit setup so the claim UPDATE (issued on a different session) can see the row.
    receipt = await create_test_receipt(db_session, family, user, image_path=str(image_file), status="failed")
    await db_session.commit()

    captured_status_when_reprocess_called: dict[str, str] = {}

    orig_reprocess = _rs.reprocess_receipt

    async def spy_reprocess(db, anth, r):
        captured_status_when_reprocess_called["status"] = r.status
        return await orig_reprocess(db, anth, r)

    # Use a production-like get_db so the claim's commit is real.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    def production_like_get_db(eng):
        async def _override() -> AsyncGenerator[AsyncSession, None]:
            session = AsyncSession(eng, expire_on_commit=False)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        return _override

    app.dependency_overrides[get_db] = production_like_get_db(engine)
    try:
        with (
            patch("app.services.receipt_service.reprocess_receipt", side_effect=spy_reprocess),
            patch(
                "app.services.receipt_service.claude_client.extract_receipt",
                AsyncMock(return_value=_extracted()),
            ),
            patch(
                "app.services.receipt_service.category_suggestion.suggest_for_store",
                AsyncMock(return_value=category),
            ),
        ):
            async with authenticated_client(user) as client:
                resp = await client.post(f"/api/families/{family.id}/receipts/{receipt.id}/retry")
    finally:
        app.dependency_overrides.pop(get_db, None)
        # Cleanup committed row so later tests don't see it.
        cleanup_session = AsyncSession(engine, expire_on_commit=False)
        try:
            await cleanup_session.execute(Receipt.__table__.delete().where(Receipt.id == receipt.id))
            await cleanup_session.commit()
        finally:
            await cleanup_session.close()
        await engine.dispose()

    assert resp.status_code == 200
    # The service layer must have observed status='processing' at reprocess time,
    # proving the atomic claim ran before reprocess.
    assert captured_status_when_reprocess_called.get("status") == "processing", (
        "reprocess_receipt must be called AFTER the failed->processing claim commits"
    )


@pytest.mark.asyncio
async def test_retry_concurrent_only_one_succeeds(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    """Two concurrent retries on the same failed receipt: exactly one sees
    the atomic UPDATE land (status=failed row), the other must get 409.
    Simulates the race by calling ``claim_receipt_for_retry`` twice against
    the same row on separate sessions.
    """
    from app.services import receipt_service as _rs

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_file = tmp_path / "receipt.jpg"
    image_file.write_bytes(VALID_JPEG)
    receipt = await create_test_receipt(db_session, family, user, image_path=str(image_file), status="failed")
    await db_session.commit()

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        session_a = AsyncSession(engine, expire_on_commit=False)
        session_b = AsyncSession(engine, expire_on_commit=False)
        try:
            # Each session re-loads the receipt so they hold separate ORM instances.
            r_a = (await session_a.execute(select(Receipt).where(Receipt.id == receipt.id))).scalar_one()
            r_b = (await session_b.execute(select(Receipt).where(Receipt.id == receipt.id))).scalar_one()

            # First claim wins.
            await _rs.claim_receipt_for_retry(session_a, r_a)
            assert r_a.status == "processing"

            # Second claim observes status='processing' and must 409.
            from fastapi import HTTPException as _HTTPExc

            with pytest.raises(_HTTPExc) as excinfo:
                await _rs.claim_receipt_for_retry(session_b, r_b)
            assert excinfo.value.status_code == 409
            assert "processing" in excinfo.value.detail
        finally:
            await session_a.close()
            await session_b.close()
            # Cleanup committed row so later tests don't see it.
            cleanup_session = AsyncSession(engine, expire_on_commit=False)
            try:
                await cleanup_session.execute(Receipt.__table__.delete().where(Receipt.id == receipt.id))
                await cleanup_session.commit()
            finally:
                await cleanup_session.close()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# DELETE /api/families/{family_id}/receipts/{receipt_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_receipt_by_uploader_returns_204(
    db_session: AsyncSession, authenticated_client, tmp_path: Path
) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    image_file = tmp_path / "receipt.jpg"
    image_file.write_bytes(b"data")
    receipt = await create_test_receipt(db_session, family, user, image_path=str(image_file), status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.delete(f"/api/families/{family.id}/receipts/{receipt.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 204
    assert not image_file.exists()


@pytest.mark.asyncio
async def test_delete_receipt_by_non_uploader_member_returns_403(
    db_session: AsyncSession, authenticated_client
) -> None:
    from app.main import app

    owner = await create_test_user(db_session)
    other = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, owner)

    member = FamilyMember(
        id=uuid.uuid4(),
        family_id=family.id,
        user_id=other.id,
        role="member",
        joined_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    receipt = await create_test_receipt(db_session, family, owner, status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(other) as client:
            resp = await client.delete(f"/api/families/{family.id}/receipts/{receipt.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_receipt_by_admin_returns_204(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    uploader = await create_test_user(db_session)
    admin = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, admin)

    member = FamilyMember(
        id=uuid.uuid4(),
        family_id=family.id,
        user_id=uploader.id,
        role="member",
        joined_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(member)
    await db_session.flush()

    receipt = await create_test_receipt(db_session, family, uploader, image_path=None, status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(admin) as client:
            resp = await client.delete(f"/api/families/{family.id}/receipts/{receipt.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 204
