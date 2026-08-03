"""User service: create or update a user on Google OAuth login."""

from datetime import datetime, timezone

from app.logging import get_logger
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork

logger = get_logger(__name__)


async def upsert_user(
    uow: UnitOfWork,
    google_id: str,
    email: str,
    display_name: str,
    avatar_url: str | None,
) -> tuple[User, bool]:
    """Create or update a user from Google OAuth login data.

    Returns a ``(user, is_new_user)`` tuple where ``is_new_user`` is ``True``
    when the user did not previously exist.

    The update branch has no ``add``: it mutates the instance the repository
    returned and lets dirty tracking carry the write, exactly as the raw-session
    version did.
    """
    user = await uow.users.get_by_google_id(google_id)

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
        uow.users.add(user)
        await uow.flush()
        logger.info("user_created", google_id=google_id, email=email)
        return user, True

    user.last_login_at = now
    user.display_name = display_name
    user.avatar_url = avatar_url
    await uow.flush()
    logger.info("user_updated", google_id=google_id, email=email)
    return user, False
