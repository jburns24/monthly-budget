"""Tests for the receipt upload rate limiter service.

Covers:
- Allows request and returns count when under the limit
- Blocks request when at or over the limit
- Fails open (allows request) on Redis errors
- Uses the correct Redis key format
- Handles first upload (count=1 after INCR)
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rate_limiter import check_and_increment_receipt_upload


@pytest.fixture
def family_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


async def _make_pipeline_mock(incr_result: int) -> MagicMock:
    """Return an AsyncMock Redis pipeline that returns incr_result from INCR."""
    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.ttl = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[incr_result, 1, 86399])
    return pipe


async def test_allows_first_upload(family_id: uuid.UUID) -> None:
    """First upload of the day is allowed with count=1."""
    pipe = await _make_pipeline_mock(1)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is True
    assert count == 1


async def test_allows_upload_at_limit_minus_one(family_id: uuid.UUID) -> None:
    """Upload at count=49 (one below limit of 50) is allowed."""
    pipe = await _make_pipeline_mock(49)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is True
    assert count == 49


async def test_allows_upload_at_exact_limit(family_id: uuid.UUID) -> None:
    """Upload that reaches exactly the limit is still allowed (50th upload of 50 allowed)."""
    pipe = await _make_pipeline_mock(50)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is True
    assert count == 50


async def test_blocks_upload_over_limit(family_id: uuid.UUID) -> None:
    """Upload that exceeds the limit (count=51 when limit=50) is blocked."""
    pipe = await _make_pipeline_mock(51)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is False
    assert count == 51


async def test_fails_open_on_redis_error(family_id: uuid.UUID) -> None:
    """Redis connection error causes fail-open: request allowed, count=0."""
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(side_effect=Exception("Redis connection refused"))

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is True
    assert count == 0


async def test_fails_open_on_pipeline_execute_error(family_id: uuid.UUID) -> None:
    """Redis pipeline execute error causes fail-open: request allowed, count=0."""
    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.ttl = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(side_effect=Exception("Redis timeout"))
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id, limit=50)

    assert allowed is True
    assert count == 0


async def test_uses_correct_redis_key_format(family_id: uuid.UUID) -> None:
    """Redis key includes family_id and today's date in YYYY-MM-DD format."""
    pipe = await _make_pipeline_mock(1)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    today = date.today().strftime("%Y-%m-%d")
    expected_key = f"receipts:uploads:{family_id}:{today}"

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        await check_and_increment_receipt_upload(family_id, limit=50)

    pipe.incr.assert_called_once_with(expected_key)


async def test_pipeline_sets_expire_on_key(family_id: uuid.UUID) -> None:
    """Pipeline calls EXPIRE with 86400 seconds (24 hours) on the key."""
    pipe = await _make_pipeline_mock(1)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    today = date.today().strftime("%Y-%m-%d")
    expected_key = f"receipts:uploads:{family_id}:{today}"

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        await check_and_increment_receipt_upload(family_id, limit=50)

    pipe.expire.assert_called_once_with(expected_key, 86400)


async def test_default_limit_is_50(family_id: uuid.UUID) -> None:
    """Default limit of 50 blocks request at count=51 without explicit limit arg."""
    pipe = await _make_pipeline_mock(51)
    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe)

    with patch("app.services.rate_limiter._get_redis_client", return_value=client_mock):
        allowed, count = await check_and_increment_receipt_upload(family_id)

    assert allowed is False
    assert count == 51
