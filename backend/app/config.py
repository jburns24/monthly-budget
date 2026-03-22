"""Application configuration loaded from environment variables."""

from pydantic import Field
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
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/monthly_budget",
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

    @property
    def is_production(self) -> bool:
        """Return True if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Return True if running in development environment."""
        return self.environment.lower() == "development"


settings = Settings()
