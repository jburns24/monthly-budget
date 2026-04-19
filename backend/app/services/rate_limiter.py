"""Per-family daily receipt upload rate limiter backed by Redis.

Fails open: if Redis is unavailable, the request is allowed and a warning is logged.
"""

import uuid
from datetime import date

import redis.asyncio as aioredis

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


def _get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=False)


async def check_and_increment_receipt_upload(
    family_id: uuid.UUID,
    limit: int = 50,
) -> tuple[bool, int]:
    """Check and increment the daily receipt upload count for a family.

    Uses a Redis pipeline (INCR + EXPIRE + TTL) so the counter and TTL are set
    atomically. The key expires after 24 hours, resetting the counter each day.

    Returns
    -------
    tuple[bool, int]
        ``(allowed, count)`` where ``allowed`` is True when count <= limit,
        and ``count`` is the post-increment value. On Redis failure, returns
        ``(True, 0)`` (fail-open).
    """
    today = date.today().strftime("%Y-%m-%d")
    key = f"receipts:uploads:{family_id}:{today}"

    try:
        client = _get_redis_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        pipe.ttl(key)
        results = await pipe.execute()
        count: int = results[0]
        return count <= limit, count
    except Exception as exc:
        logger.warning(
            "rate_limiter_redis_error",
            family_id=str(family_id),
            error=str(exc),
        )
        return True, 0
