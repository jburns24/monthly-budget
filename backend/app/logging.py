"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog

from app.config import settings

_SENSITIVE_KEYS = frozenset({"anthropic_api_key", "jwt_secret", "google_client_secret", "password", "authorization"})


def _sensitive_filter(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys from structlog event dicts before they are rendered."""
    for key in _SENSITIVE_KEYS:
        if key in event_dict:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    """Configure structlog with appropriate renderer based on environment."""

    shared_processors: list[structlog.types.Processor] = [
        _sensitive_filter,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON output for production — machine-readable
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Human-readable colored output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG if settings.debug else logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given name."""
    return structlog.get_logger(name)
