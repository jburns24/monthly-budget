"""Unit tests for user_service against the in-memory adapter. No database.

``upsert_user`` had no direct test before Step 7.5 — it was covered only through
``tests/test_auth.py``'s two ``/api/auth/callback`` cases, which need Postgres, a
mocked Google, and a patched JWT secret to assert one boolean. Moving the service
onto ``uow.users`` makes the branch testable on its own.
"""

import uuid

from app.services.user_service import upsert_user
from tests.unit.conftest import make_user, seed


async def test_upsert_creates_a_user_that_does_not_exist(uow) -> None:
    """First login inserts the row and reports the user as new."""
    user, is_new_user = await upsert_user(
        uow,
        google_id="google_new",
        email="new@example.com",
        display_name="New User",
        avatar_url="https://example.com/pic.jpg",
    )

    assert is_new_user is True
    assert user.google_id == "google_new"
    assert user.email == "new@example.com"
    assert user.display_name == "New User"
    assert user.avatar_url == "https://example.com/pic.jpg"


async def test_a_created_user_is_flushed_and_readable(uow) -> None:
    """The router reads ``user.id`` to mint a JWT, so the insert must be flushed."""
    user, _ = await upsert_user(
        uow,
        google_id="google_new",
        email="new@example.com",
        display_name="New User",
        avatar_url=None,
    )

    assert isinstance(user.id, uuid.UUID)
    assert await uow.users.get(user.id) is not None


async def test_upsert_updates_the_existing_user_in_place(uow) -> None:
    """A returning login refreshes the profile rather than inserting a second row."""
    existing = make_user(google_id="google_known", email="known@example.com", display_name="Old Name")
    await seed(uow, existing)

    user, is_new_user = await upsert_user(
        uow,
        google_id="google_known",
        email="known@example.com",
        display_name="New Name",
        avatar_url="https://example.com/new.jpg",
    )

    assert is_new_user is False
    assert user.id == existing.id
    assert user.display_name == "New Name"
    assert user.avatar_url == "https://example.com/new.jpg"
    assert len(uow.store.rows(type(existing))) == 1


async def test_upsert_stamps_last_login_at_on_a_returning_user(uow) -> None:
    """``last_login_at`` is what the grace-period logic reads; it must move."""
    existing = make_user(google_id="google_known")
    await seed(uow, existing)
    assert existing.last_login_at is None

    user, _ = await upsert_user(
        uow,
        google_id="google_known",
        email=existing.email,
        display_name=existing.display_name,
        avatar_url=None,
    )

    assert user.last_login_at is not None


async def test_upsert_clears_an_avatar_google_no_longer_sends(uow) -> None:
    """``avatar_url=None`` overwrites, matching the pre-port assignment."""
    existing = make_user(google_id="google_known")
    existing.avatar_url = "https://example.com/old.jpg"
    await seed(uow, existing)

    user, _ = await upsert_user(
        uow,
        google_id="google_known",
        email=existing.email,
        display_name=existing.display_name,
        avatar_url=None,
    )

    assert user.avatar_url is None
