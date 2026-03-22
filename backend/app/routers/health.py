"""Health check endpoints for the Monthly Budget API."""

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.database import engine
from app.logging import get_logger

router = APIRouter(prefix="/api/health", tags=["health"])

logger = get_logger(__name__)


async def _check_database() -> tuple[bool, str]:
    """Check if the database is reachable. Returns (ok, status_string)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:
        logger.warning("database_health_check_failed", error=str(exc))
        return False, "unreachable"


async def _check_redis() -> tuple[bool, str]:
    """Check if Redis is reachable. Returns (ok, status_string)."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return True, "connected"
    except Exception as exc:
        logger.warning("redis_health_check_failed", error=str(exc))
        return False, "unreachable"


@router.get("")
async def health(response: Response) -> dict:
    """Return overall service health including database and Redis connectivity."""
    db_ok, db_status = await _check_database()
    redis_ok, redis_status = await _check_redis()

    all_ok = db_ok and redis_ok
    if not all_ok:
        response.status_code = 503

    return {
        "status": "healthy" if all_ok else "degraded",
        "database": db_status,
        "redis": redis_status,
    }


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Return 200 only when the service is ready to accept traffic.

    Checks that the database is reachable as a lightweight readiness probe.
    A full Alembic migration check can be wired in here once Alembic is
    configured (T01.4).
    """
    db_ok, db_status = await _check_database()

    if not db_ok:
        response.status_code = 503
        return {"status": "not_ready", "database": db_status}

    return {"status": "ready", "database": db_status}
