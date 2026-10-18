"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so it works regardless of CWD.
# config.py lives at backend/app/config.py → parent.parent.parent = repo root.
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_env_file),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/monthly_budget",  # pragma: allowlist secret
        description="Async PostgreSQL connection URL",
    )
    database_migration_url: str = Field(
        default="",
        description=(
            "Async PostgreSQL connection URL used by Alembic. Falls back to "
            "database_url when unset. Needed for hosted Supabase: the Supavisor "
            "transaction pooler (port 6543) rejects the named prepared statements "
            "Alembic's DDL requires, so migrations must target the session pooler "
            "(port 5432) or a direct connection instead."
        ),
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
    jwt_access_token_expire_minutes: int = Field(
        default=15,
        description="Access JWT lifetime in minutes (short-lived; refreshed via refresh cookie)",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh JWT lifetime in days (bounds the overall signed-in session)",
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
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for receipt scanning",
    )
    llm_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL of the OpenAI-compatible chat completions API used for receipt scanning",
    )
    llm_model: str = Field(
        default="anthropic/claude-haiku-5.5",
        description="Model slug sent to the LLM provider for receipt extraction",
    )
    llm_http_referer: str = Field(
        default="",
        description="Optional HTTP-Referer header (OpenRouter app attribution)",
    )
    llm_app_title: str = Field(
        default="",
        description="Optional X-Title header (OpenRouter app attribution)",
    )
    llm_mock: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_mock", "anthropic_mock"),
        description="When True, skip real LLM calls and return deterministic mock responses",
    )
    llm_mock_scenario: str = Field(
        default="success",
        validation_alias=AliasChoices("llm_mock_scenario", "anthropic_mock_scenario"),
        description="Mock scenario to use when llm_mock=True (success, medium_confidence, low_confidence, non_receipt, api_error)",
    )

    decision_model: str = Field(
        default="microsoft/microsoft-decision-1",
        description="OpenRouter System One decision model used to suggest an expense category from its description",
    )
    decision_min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum decision-model confidence for a category suggestion to be returned",
    )
    decision_timeout_seconds: float = Field(
        default=3.0,
        gt=0.0,
        description="Timeout for the category-suggestion decision call; it is never retried",
    )
    decision_mock: bool = Field(
        default=False,
        description="When True, skip the real decision-model call and return a deterministic suggestion",
    )
    decision_mock_scenario: str = Field(
        default="success",
        description="Mock scenario when decision_mock=True (success, low_confidence, api_error)",
    )

    hpi_auto_refresh: bool = Field(
        default=True,
        description=(
            "When True, asset requests schedule a background download of the FHFA house price index if the "
            "local copy is missing or older than 7 days. Tests turn this off so nothing touches the network."
        ),
    )

    @model_validator(mode="after")
    def apply_database_migration_url_fallback(self) -> "Settings":
        """Default database_migration_url to database_url when unset."""
        if not self.database_migration_url:
            self.database_migration_url = self.database_url
        return self

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
