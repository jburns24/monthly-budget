"""Unit tests for User and RefreshTokenBlacklist ORM models.

These tests verify that the models map correctly to the database schema,
including field types, constraints, defaults, and relationships.

Each test uses a local db_session fixture that creates a fresh NullPool
connection per test to avoid event-loop/pool conflicts with pytest-asyncio's
per-function event loop scope.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.refresh_token_blacklist import RefreshTokenBlacklist  # noqa: F401 — registers with Base.metadata
from app.models.user import User
from tests.conftest import create_test_user

# ---------------------------------------------------------------------------
# Local fixture: NullPool engine avoids event-loop conflicts across tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session with per-test NullPool engine and transaction rollback.

    Using NullPool prevents asyncpg connections from being re-used across
    pytest-asyncio's per-function event loops, eliminating 'Future attached
    to a different loop' errors.
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
# User model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_create_and_read(db_session: AsyncSession) -> None:
    """User can be inserted and retrieved with all fields intact."""
    now = datetime.now(tz=timezone.utc)
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        google_id="google_abc123",
        email="alice@example.com",
        display_name="Alice",
        avatar_url="https://example.com/alice.jpg",
        timezone="America/Chicago",
        created_at=now,
        last_login_at=now,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    fetched = await db_session.get(User, user_id)
    assert fetched is not None
    assert fetched.id == user_id
    assert fetched.google_id == "google_abc123"
    assert fetched.email == "alice@example.com"
    assert fetched.display_name == "Alice"
    assert fetched.avatar_url == "https://example.com/alice.jpg"
    assert fetched.timezone == "America/Chicago"


@pytest.mark.asyncio
async def test_user_uuid_pk_generation(db_session: AsyncSession) -> None:
    """User.id is auto-generated as a UUID when not explicitly provided."""
    user = User(
        google_id="google_uuid_test",
        email="uuid_test@example.com",
        display_name="UUID Test",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)


@pytest.mark.asyncio
async def test_user_default_timezone(db_session: AsyncSession) -> None:
    """User.timezone defaults to 'America/New_York' when not provided."""
    user = User(
        google_id="google_tz_test",
        email="tz_test@example.com",
        display_name="TZ Test",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.timezone == "America/New_York"


@pytest.mark.asyncio
async def test_user_avatar_url_nullable(db_session: AsyncSession) -> None:
    """User.avatar_url is nullable."""
    user = User(
        google_id="google_no_avatar",
        email="no_avatar@example.com",
        display_name="No Avatar",
        avatar_url=None,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.avatar_url is None


@pytest.mark.asyncio
async def test_user_google_id_unique_constraint(db_session: AsyncSession) -> None:
    """Inserting two users with the same google_id raises IntegrityError."""
    await create_test_user(db_session, google_id="google_dup", email="first@example.com")

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(User(google_id="google_dup", email="second@example.com", display_name="Dup"))
            await db_session.flush()


@pytest.mark.asyncio
async def test_user_email_unique_constraint(db_session: AsyncSession) -> None:
    """Inserting two users with the same email raises IntegrityError."""
    await create_test_user(db_session, google_id="google_first", email="shared@example.com")

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(User(google_id="google_second", email="shared@example.com", display_name="Dup"))
            await db_session.flush()


# ---------------------------------------------------------------------------
# RefreshTokenBlacklist model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blacklist_create_and_read(db_session: AsyncSession) -> None:
    """RefreshTokenBlacklist entry can be inserted and retrieved."""
    user = await create_test_user(db_session)
    expires = datetime.now(tz=timezone.utc) + timedelta(days=7)

    entry = RefreshTokenBlacklist(
        jti="test_jti_001",
        user_id=user.id,
        expires_at=expires,
    )
    db_session.add(entry)
    await db_session.flush()
    await db_session.refresh(entry)

    fetched = await db_session.get(RefreshTokenBlacklist, entry.id)
    assert fetched is not None
    assert fetched.jti == "test_jti_001"
    assert fetched.user_id == user.id
    assert fetched.expires_at is not None


@pytest.mark.asyncio
async def test_blacklist_uuid_pk_generation(db_session: AsyncSession) -> None:
    """RefreshTokenBlacklist.id is auto-generated as a UUID."""
    user = await create_test_user(db_session)
    entry = RefreshTokenBlacklist(
        jti="jti_uuid_gen",
        user_id=user.id,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
    )
    db_session.add(entry)
    await db_session.flush()
    await db_session.refresh(entry)

    assert entry.id is not None
    assert isinstance(entry.id, uuid.UUID)


@pytest.mark.asyncio
async def test_blacklist_fk_to_user(db_session: AsyncSession) -> None:
    """RefreshTokenBlacklist.user_id is a valid FK to users.id."""
    user = await create_test_user(db_session)
    entry = RefreshTokenBlacklist(
        jti="jti_fk_test",
        user_id=user.id,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await db_session.execute(select(RefreshTokenBlacklist).where(RefreshTokenBlacklist.user_id == user.id))
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].jti == "jti_fk_test"


@pytest.mark.asyncio
async def test_blacklist_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a user cascades to delete their blacklist entries."""
    user = await create_test_user(db_session)
    entry = RefreshTokenBlacklist(
        jti="jti_cascade",
        user_id=user.id,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
    )
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id

    await db_session.delete(user)
    await db_session.flush()
    db_session.expunge_all()  # Clear identity map so get() queries the DB

    deleted = await db_session.get(RefreshTokenBlacklist, entry_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_blacklist_jti_unique_constraint(db_session: AsyncSession) -> None:
    """Inserting two blacklist entries with the same jti raises IntegrityError."""
    user = await create_test_user(db_session)
    expires = datetime.now(tz=timezone.utc) + timedelta(days=1)

    db_session.add(RefreshTokenBlacklist(jti="dup_jti", user_id=user.id, expires_at=expires))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(RefreshTokenBlacklist(jti="dup_jti", user_id=user.id, expires_at=expires))
            await db_session.flush()


@pytest.mark.asyncio
async def test_blacklist_indexes_exist(db_session: AsyncSession) -> None:
    """Indexes on jti and expires_at exist in the database."""
    result = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'refresh_token_blacklist' ORDER BY indexname")
    )
    indexes = {row[0] for row in result.fetchall()}
    assert "ix_refresh_token_blacklist_jti" in indexes
    assert "ix_refresh_token_blacklist_expires_at" in indexes


@pytest.mark.asyncio
async def test_blacklist_fk_rejects_missing_user(db_session: AsyncSession) -> None:
    """Inserting a blacklist entry with a non-existent user_id raises IntegrityError."""
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            entry = RefreshTokenBlacklist(
                jti="jti_no_user",
                user_id=uuid.uuid4(),
                expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
            )
            db_session.add(entry)
            await db_session.flush()
