"""Unit tests for the in-memory UserRepository. No database."""

import uuid

from tests.unit.conftest import make_user, seed


async def test_flush_assigns_id(uow) -> None:
    """id is a Python-side default (uuid4); the fake must supply it like Postgres would.

    Unlike Category, User.created_at has no default at all — every call site
    (user_service.upsert_user, dev_login) sets it explicitly, so the store has
    nothing to fake there.
    """
    user = make_user()
    assert user.id is None

    uow.users.add(user)
    await uow.flush()

    assert isinstance(user.id, uuid.UUID)


async def test_get_returns_the_user(uow) -> None:
    """get finds a user by primary key."""
    user = make_user(display_name="Alice")
    await seed(uow, user)

    found = await uow.users.get(user.id)

    assert found is not None
    assert found.display_name == "Alice"


async def test_get_returns_none_for_an_unknown_id(uow) -> None:
    """A missing id is None, not an error."""
    assert await uow.users.get(uuid.uuid4()) is None


async def test_get_by_google_id_finds_the_user(uow) -> None:
    """get_by_google_id backs the OAuth login upsert."""
    user = make_user(google_id="google_123")
    await seed(uow, user)

    found = await uow.users.get_by_google_id("google_123")

    assert found is not None
    assert found.id == user.id


async def test_get_by_google_id_returns_none_when_no_match(uow) -> None:
    """An unknown google_id returns None, not an error."""
    assert await uow.users.get_by_google_id("nope") is None


async def test_get_by_email_finds_the_user(uow) -> None:
    """get_by_email backs the invite-by-email lookup."""
    user = make_user(email="alice@example.com")
    await seed(uow, user)

    found = await uow.users.get_by_email("alice@example.com")

    assert found is not None
    assert found.id == user.id


async def test_get_by_email_returns_none_when_no_match(uow) -> None:
    """An unknown email returns None, not an error."""
    assert await uow.users.get_by_email("nobody@example.com") is None


async def test_mutating_a_returned_instance_is_tracked_without_an_explicit_add(uow) -> None:
    """Services rely on implicit dirty tracking: ``user.display_name = x; await flush()``."""
    user = make_user(display_name="Before")
    await seed(uow, user)

    fetched = await uow.users.get(user.id)
    fetched.display_name = "After"
    await uow.flush()

    again = await uow.users.get(user.id)
    assert again.display_name == "After"
