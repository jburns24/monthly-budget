"""Tests for Settings.database_migration_url fallback behaviour."""

from app.config import Settings


def test_database_migration_url_falls_back_to_database_url() -> None:
    """Unset DATABASE_MIGRATION_URL falls back to database_url."""
    s = Settings(_env_file=None, database_url="postgresql+asyncpg://a:b@localhost:5432/x")  # type: ignore[call-arg]
    assert s.database_migration_url == s.database_url


def test_database_migration_url_explicit_value_is_preserved() -> None:
    """An explicit DATABASE_MIGRATION_URL is not overridden by database_url."""
    migration_url = "postgresql+asyncpg://a:b@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+asyncpg://a:b@localhost:5432/x",
        database_migration_url=migration_url,
    )
    assert s.database_migration_url == migration_url
