"""Tests for T02.1: AsyncAnthropic lifespan singleton + config settings."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings, settings

# These two assert on the declared field *defaults*, so they read the field
# definitions rather than a constructed Settings. Reading the global settings
# made them fail for anyone whose .env set ANTHROPIC_MOCK=true, even though the
# defaults were untouched. Going through model_fields is independent of both
# .env and real environment variables. CI has neither, so nothing changes there.


def test_anthropic_mock_setting_defaults_to_false() -> None:
    """Settings.anthropic_mock defaults to False."""
    assert Settings.model_fields["anthropic_mock"].default is False


def test_anthropic_mock_scenario_defaults_to_success() -> None:
    """Settings.anthropic_mock_scenario defaults to 'success'."""
    assert Settings.model_fields["anthropic_mock_scenario"].default == "success"


def test_anthropic_api_key_setting_exists() -> None:
    """Settings.anthropic_api_key field exists."""
    assert hasattr(settings, "anthropic_api_key")
    assert isinstance(settings.anthropic_api_key, str)


def test_get_anthropic_client_dependency_importable() -> None:
    """get_anthropic_client dependency is importable from app.dependencies."""
    from app.dependencies import get_anthropic_client  # noqa: F401

    assert callable(get_anthropic_client)


@pytest.mark.asyncio
async def test_lifespan_sets_anthropic_on_app_state() -> None:
    """FastAPI lifespan sets app.state.anthropic during startup and calls close() on shutdown."""
    from fastapi import FastAPI

    from app.main import lifespan

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    test_app = FastAPI(lifespan=lifespan)

    with patch("app.main.AsyncAnthropic", return_value=mock_client) as mock_cls:
        async with lifespan(test_app):
            assert test_app.state.anthropic is mock_client
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["max_retries"] == 2
            assert call_kwargs["timeout"].connect == 10.0
            assert call_kwargs["timeout"].read == 45.0

    mock_client.close.assert_awaited_once()


def test_lifespan_anthropic_constructor_kwargs() -> None:
    """AsyncAnthropic is called with the expected constructor arguments in lifespan."""
    import inspect

    import app.main as main_module

    source = inspect.getsource(main_module.lifespan)
    assert "max_retries=2" in source
    assert "api_key=settings.anthropic_api_key" in source
    assert "read=45.0" in source
    assert "connect=10.0" in source
    assert "app.state.anthropic" in source
    assert "app.state.anthropic.close()" in source


@pytest.mark.asyncio
async def test_get_anthropic_client_returns_app_state_client() -> None:
    """get_anthropic_client dependency returns the client stored in app.state."""
    from unittest.mock import MagicMock

    from fastapi import Request

    from app.dependencies import get_anthropic_client

    mock_client = MagicMock()
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.anthropic = mock_client

    result = get_anthropic_client(mock_request)
    assert result is mock_client
