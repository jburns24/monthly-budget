"""Application configuration loaded from environment variables."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/monthly_budget",  # pragma: allowlist secret
        description="Async PostgreSQL connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Application
    environment: str = Field(
        default="development",
        description="Runtime environment (development, staging, production)",
    )
    app_name: str = Field(
        default="monthly-budget-api",
        description="Application name used in logs and metrics",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # API
    api_prefix: str = Field(
        default="/api",
        description="API route prefix",
    )

    # Secrets (used in later epics, but accepted now to avoid startup errors)
    secret_key: str = Field(
        default="",
        description="Application secret key",
    )
    jwt_secret: str = Field(
        default="",
        description="JWT signing secret",
    )
    google_client_id: str = Field(
        default="",
        description="Google OAuth 2.0 client ID",
    )
    google_client_secret: str = Field(
        default="",
        description="Google OAuth 2.0 client secret",
    )
    google_redirect_uri: str = Field(
        default="http://localhost:5173/auth/callback",
        description="Google OAuth 2.0 redirect URI (must match frontend callback route)",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for receipt scanning",
    )

    @model_validator(mode="after")
    def validate_auth_secrets(self) -> "Settings":
        """Fail fast on missing/weak auth secrets outside development and test."""
        env = self.environment.lower()
        if env not in ("development", "test"):
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError("jwt_secret must be at least 32 characters in non-development environments")
            if not self.google_client_id:
                raise ValueError("google_client_id must be set in non-development environments")
        return self

    @property
    def is_production(self) -> bool:
        """Return True if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Return True if running in development environment."""
        return self.environment.lower() == "development"


settings = Settings()
