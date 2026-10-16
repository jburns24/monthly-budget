"""Tests for the AsyncOpenAI (OpenRouter) lifespan singleton + LLM config settings."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings, settings

# These assert on the declared field *defaults*, so they read the field
# definitions rather than a constructed Settings: a developer .env setting
# LLM_MOCK=true must not fail them.


def test_llm_mock_setting_defaults_to_false() -> None:
    assert Settings.model_fields["llm_mock"].default is False


def test_llm_mock_scenario_defaults_to_success() -> None:
    assert Settings.model_fields["llm_mock_scenario"].default == "success"


def test_llm_base_url_defaults_to_openrouter() -> None:
    assert Settings.model_fields["llm_base_url"].default == "https://openrouter.ai/api/v1"


def test_llm_model_defaults_to_haiku_slug() -> None:
    assert Settings.model_fields["llm_model"].default == "anthropic/claude-haiku-5.5"


def test_openrouter_api_key_setting_exists() -> None:
    assert isinstance(settings.openrouter_api_key, str)


def test_anthropic_workspace_id_removed() -> None:
    assert "anthropic_workspace_id" not in Settings.model_fields


@pytest.mark.parametrize(
    ("env_name", "scenario_env"),
    [("LLM_MOCK", "LLM_MOCK_SCENARIO"), ("ANTHROPIC_MOCK", "ANTHROPIC_MOCK_SCENARIO")],
)
def test_mock_settings_accept_new_and_legacy_env_names(
    monkeypatch: pytest.MonkeyPatch, env_name: str, scenario_env: str
) -> None:
    """The renamed mock flags still honor the old ANTHROPIC_* env names."""
    for name in ("LLM_MOCK", "LLM_MOCK_SCENARIO", "ANTHROPIC_MOCK", "ANTHROPIC_MOCK_SCENARIO"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(env_name, "true")
    monkeypatch.setenv(scenario_env, "api_error")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.llm_mock is True
    assert s.llm_mock_scenario == "api_error"


def test_get_llm_client_dependency_importable() -> None:
    from app.dependencies import get_llm_client

    assert callable(get_llm_client)


@pytest.mark.asyncio
async def test_lifespan_sets_llm_on_app_state() -> None:
    """Lifespan builds one AsyncOpenAI at startup and closes it on shutdown."""
    from fastapi import FastAPI

    from app.main import lifespan

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    test_app = FastAPI(lifespan=lifespan)

    with (
        patch("app.main.AsyncOpenAI", return_value=mock_client) as mock_cls,
        patch("app.main.settings.llm_http_referer", ""),
        patch("app.main.settings.llm_app_title", ""),
    ):
        async with lifespan(test_app):
            assert test_app.state.llm is mock_client
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["base_url"] == settings.llm_base_url
            assert call_kwargs["api_key"] == settings.openrouter_api_key
            assert call_kwargs["default_headers"] is None
            assert call_kwargs["max_retries"] == 2
            assert call_kwargs["timeout"].connect == 10.0
            assert call_kwargs["timeout"].read == 45.0

    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_sends_attribution_headers_when_configured() -> None:
    from fastapi import FastAPI

    from app.main import lifespan

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    with (
        patch("app.main.AsyncOpenAI", return_value=mock_client) as mock_cls,
        patch("app.main.settings.llm_http_referer", "https://budget.example"),
        patch("app.main.settings.llm_app_title", "Monthly Budget"),
    ):
        async with lifespan(FastAPI(lifespan=lifespan)):
            headers = mock_cls.call_args.kwargs["default_headers"]

    assert headers == {"HTTP-Referer": "https://budget.example", "X-Title": "Monthly Budget"}


def test_get_llm_client_returns_app_state_client() -> None:
    from fastapi import Request

    from app.dependencies import get_llm_client

    mock_client = MagicMock()
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.llm = mock_client

    assert get_llm_client(mock_request) is mock_client
