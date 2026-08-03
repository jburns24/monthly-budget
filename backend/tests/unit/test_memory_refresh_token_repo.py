"""Unit tests for the in-memory RefreshTokenRepository. No database."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.ports.errors import UniqueViolation
from tests.unit.conftest import make_refresh_token, seed


async def test_flush_assigns_id(uow) -> None:
    """id is a Python-side default (uuid4); the fake must supply it like Postgres would.

    ``created_at`` is nullable with no default at all, like ``User.created_at`` —
    the logout path sets it explicitly — so the store has nothing to fake there.
    """
    entry = make_refresh_token(uuid.uuid4(), jti="jti_1")
    assert entry.id is None

    uow.tokens.add(entry)
    await uow.flush()

    assert isinstance(entry.id, uuid.UUID)


async def test_is_blacklisted_is_false_for_an_unknown_jti(uow) -> None:
    """A jti nobody revoked is not blacklisted."""
    assert await uow.tokens.is_blacklisted("never_seen") is False


async def test_is_blacklisted_is_true_for_a_revoked_jti(uow) -> None:
    """The jti logout recorded is the one /refresh must reject."""
    await seed(uow, make_refresh_token(uuid.uuid4(), jti="revoked"))

    assert await uow.tokens.is_blacklisted("revoked") is True


async def test_is_blacklisted_matches_the_jti_not_the_user(uow) -> None:
    """Revoking one token does not revoke the user's other tokens."""
    user_id = uuid.uuid4()
    await seed(uow, make_refresh_token(user_id, jti="revoked"))

    assert await uow.tokens.is_blacklisted("still_valid") is False


async def test_added_entries_are_invisible_until_flush(uow) -> None:
    """Staged writes are not readable, matching the real session's autoflush=False."""
    uow.tokens.add(make_refresh_token(uuid.uuid4(), jti="pending"))

    assert await uow.tokens.is_blacklisted("pending") is False

    await uow.flush()

    assert await uow.tokens.is_blacklisted("pending") is True


async def test_duplicate_jti_is_a_unique_violation(uow) -> None:
    """``jti`` is ``Column(unique=True)``; the store derives that from the mapper.

    An anonymous single-column unique constraint, so this also pins that the
    spec builder picks those up without a named constraint to key off.
    """
    user_id = uuid.uuid4()
    await seed(uow, make_refresh_token(user_id, jti="dup"))

    uow.tokens.add(make_refresh_token(user_id, jti="dup"))

    with pytest.raises(UniqueViolation):
        await uow.flush()


async def test_is_blacklisted_ignores_expiry(uow) -> None:
    """An expired blacklist row still blocks the jti.

    The endpoint decodes the token before asking, so an expired refresh token is
    already rejected by ``jwt.ExpiredSignatureError``. Filtering on
    ``expires_at`` here would be a behaviour change the inline query never made —
    it selected on ``jti`` alone.
    """
    past = datetime.now(tz=timezone.utc) - timedelta(days=30)
    await seed(uow, make_refresh_token(uuid.uuid4(), jti="long_expired", expires_at=past))

    assert await uow.tokens.is_blacklisted("long_expired") is True
