"""Tests for T06: SensitiveFilter structlog processor."""

from app.logging import _sensitive_filter


def test_api_key_redacted() -> None:
    """SensitiveFilter redacts anthropic_api_key so it never appears in logs."""
    event_dict = {
        "event": "request_started",
        "anthropic_api_key": "test-anthropic-key-not-real",  # pragma: allowlist secret
        "safe_field": "visible_value",
    }
    result = _sensitive_filter(None, "info", event_dict)
    assert result["anthropic_api_key"] == "[REDACTED]"
    assert result["safe_field"] == "visible_value"
    assert result["event"] == "request_started"


def test_all_sensitive_keys_redacted() -> None:
    """All keys in _SENSITIVE_KEYS are redacted to [REDACTED]."""
    event_dict = {
        "anthropic_api_key": "test-anthropic-key-not-real",  # pragma: allowlist secret
        "jwt_secret": "test-jwt-secret-not-real",  # pragma: allowlist secret
        "google_client_secret": "test-google-secret-not-real",  # pragma: allowlist secret
        "password": "test-password-not-real",  # pragma: allowlist secret
        "authorization": "Bearer test-token-not-real",
        "event": "startup",
        "unrelated_field": "kept",
    }
    result = _sensitive_filter(None, "info", event_dict)
    assert result["anthropic_api_key"] == "[REDACTED]"
    assert result["jwt_secret"] == "[REDACTED]"
    assert result["google_client_secret"] == "[REDACTED]"
    assert result["password"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["unrelated_field"] == "kept"
    assert result["event"] == "startup"


def test_missing_sensitive_keys_are_not_added() -> None:
    """SensitiveFilter does not inject sensitive keys that were not in the dict."""
    event_dict = {"event": "boot", "level": "info"}
    result = _sensitive_filter(None, "info", event_dict)
    assert "anthropic_api_key" not in result
    assert "password" not in result
    assert result == {"event": "boot", "level": "info"}
