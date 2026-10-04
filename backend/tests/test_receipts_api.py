"""API endpoint tests for all receipt router endpoints.

Tests cover every receipt router endpoint using the ``authenticated_client``
fixture with a NullPool database session override for per-test transaction
rollback.

On design doc risk (g): the prediction was that ``owns_transaction=False`` would
let the module's bespoke NullPool ``db_session`` fixture go away. Only half of
that held. The commits are handled — ``_uow_over_test_session`` below downgrades
the request's UnitOfWork so ``receipt_service``'s deliberate mid-request commits
become flushes, and per-test rollback isolation now actually works here. But the
NullPool engine stays, because it also solves event-loop isolation, which the
seam has nothing to do with; the fixture's own docstring has the details.

Three tests genuinely need a real commit and call ``_use_real_commits()`` to opt
back out — see that helper.

Endpoints tested:
  POST   /api/families/{family_id}/receipts                         — upload (201/413/415/429)
  GET    /api/families/{family_id}/receipts                         — list
  GET    /api/families/{family_id}/receipts/{receipt_id}            — get one
  DELETE /api/families/{family_id}/receipts/{receipt_id}            — delete (204/403)

Claude mock scenarios tested: success, medium_confidence, low_confidence,
non_receipt, api_error.
"""

import io
import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.config import settings
from app.database import get_db
from app.dependencies import get_anthropic_client
from app.deps.provider import get_uow
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
    """Per-test session on a private NullPool engine.

    Design doc risk (g) predicted ``owns_transaction=False`` would retire this
    fixture in favour of the shared ``db_session`` in ``tests/conftest.py``. It
    does not, and the reason is worth recording: this engine is load-bearing for
    **event-loop isolation**, which is a separate problem from the real commits.

    ``tests/conftest.py``'s ``_test_engine`` is a module-level engine with a
    default QueuePool, while pytest-asyncio gives every test its own event loop.
    A connection opened on one test's loop and returned to the pool gets handed
    to the next test on a loop that no longer exists — ``RuntimeError: Event loop
    is closed``. The root conftest drains ``app.database.engine`` after every
    test for exactly this reason but cannot drain ``_test_engine``, which its own
    fixture is still using. This module trips the hazard where others do not
    because three of its tests really commit and open extra engines against the
    same database, so its connections churn.

    Switching to the shared fixture was tried and produced 11 event-loop
    failures. NullPool means every session gets a fresh connection and disposes
    it, so nothing crosses a loop boundary.

    What ``owns_transaction=False`` *does* retire is the reason this module used
    to abandon transaction isolation altogether — see ``_uow_over_test_session``.
    """
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
def _uow_over_test_session(db_session: AsyncSession) -> Iterator[None]:
    """Give the request a UnitOfWork that flushes instead of committing.

    ``receipt_service`` is the only service in the codebase that calls
    ``uow.commit()``, and it does so deliberately — the ``_mark_failed`` audit
    row must outlive the ``HTTPException`` that follows.
    Against the shared ``db_session`` that would commit the outer transaction the
    fixture rolls back for isolation, so before the seam this module needed its
    own NullPool engine to contain the damage (design doc risk (g)).

    ``owns_transaction=False`` is the seam's answer: the same service code runs,
    but ``commit()`` degrades to ``flush()`` and per-test rollback still works.

    Installing this on ``get_uow`` rather than ``get_db`` is what keeps the
    override transparent — ``get_uow`` normally derives from ``get_db``, so
    replacing it wholesale is the only way to change ``owns_transaction``.
    """
    from app.main import app

    app.dependency_overrides[get_uow] = lambda: SqlAlchemyUnitOfWork(db_session, owns_transaction=False)
    yield
    app.dependency_overrides.pop(get_uow, None)


def _use_real_commits() -> None:
    """Drop the ``owns_transaction=False`` override so ``uow.commit()`` is real.

    For the tests whose whole claim is durability — a row that survives the
    request's rollback, or a claim visible to a second connection. They pair this
    with a ``production_like_get_db`` override, and popping the ``get_uow``
    override restores the production ``get_uow``, which derives from it with
    ``owns_transaction=True``. Those tests own their own cleanup, because the
    rows they write really are committed.
    """
    from app.main import app

    app.dependency_overrides.pop(get_uow, None)


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
async def test_upload_success_returns_201(db_session: AsyncSession, authenticated_client) -> None:
    """Happy path: 201 with receipt + expense, needs_edit=False."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family, name="Groceries")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
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
    assert body["receipt"]["image_path"] is None  # images are never stored, only the extraction
    assert body["expense_id"] is not None
    assert body["needs_edit"] is False


@pytest.mark.asyncio
async def test_upload_low_confidence_returns_201_needs_edit(db_session: AsyncSession, authenticated_client) -> None:
    """Low confidence: 201 with needs_edit=True."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
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
async def test_upload_medium_confidence_returns_201(db_session: AsyncSession, authenticated_client) -> None:
    """Medium confidence with total: 201, needs_edit=False."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    category = await create_test_category(db_session, family)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
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
async def test_upload_non_receipt_returns_422(db_session: AsyncSession, authenticated_client) -> None:
    """Non-receipt image returns 422."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
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
async def test_upload_claude_api_error_returns_503(db_session: AsyncSession, authenticated_client) -> None:
    """Claude API failure returns 503."""
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        with (
            patch("app.services.receipt_service.receipt_storage.validate_mime", return_value="image/jpeg"),
            patch(
                "app.services.receipt_service.receipt_storage.sanitize_image",
                return_value=(b"sanitized", (100, 100)),
            ),
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
# DELETE /api/families/{family_id}/receipts/{receipt_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_receipt_by_uploader_returns_204(db_session: AsyncSession, authenticated_client) -> None:
    from app.main import app

    user = await create_test_user(db_session)
    family, _ = await create_test_family(db_session, user)
    receipt = await create_test_receipt(db_session, family, user, status="completed")

    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        async with authenticated_client(user) as client:
            resp = await client.delete(f"/api/families/{family.id}/receipts/{receipt.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 204


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
