"""User service: create or update a user on Google OAuth login."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)


async def upsert_user(
    google_id: str,
    email: str,
    display_name: str,
    avatar_url: str | None,
    db: AsyncSession,
) -> tuple[User, bool]:
    """Create or update a user from Google OAuth login data.

    Returns a ``(user, is_new_user)`` tuple where ``is_new_user`` is ``True``
    when the user did not previously exist.
    """
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    now = datetime.now(tz=timezone.utc)

    if user is None:
        user = User(
            google_id=google_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.flush()
        logger.info("user_created", google_id=google_id, email=email)
        return user, True

    user.last_login_at = now
    user.display_name = display_name
    user.avatar_url = avatar_url
    await db.flush()
    logger.info("user_updated", google_id=google_id, email=email)
    return user, False
