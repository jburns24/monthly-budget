"""Unit tests for JWT creation TTLs sourced from Settings."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt

from app.config import Settings
from app.services import jwt_service
from tests.conftest import _TEST_JWT_SECRET


def _user() -> MagicMock:
    user = MagicMock()
    user.id = "11111111-1111-1111-1111-111111111111"
    user.google_id = "google-sub"
    return user


def test_settings_jwt_ttl_defaults() -> None:
    """Unset JWT TTL env vars keep the historical 15-minute / 7-day defaults."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.jwt_access_token_expire_minutes == 15
    assert s.jwt_refresh_token_expire_days == 7


def test_settings_jwt_ttl_env_overrides() -> None:
    """JWT_ACCESS_TOKEN_EXPIRE_MINUTES and JWT_REFRESH_TOKEN_EXPIRE_DAYS are honored."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_access_token_expire_minutes=60,
        jwt_refresh_token_expire_days=30,
    )
    assert s.jwt_access_token_expire_minutes == 60
    assert s.jwt_refresh_token_expire_days == 30


def test_create_access_token_uses_configured_ttl() -> None:
    """Access token exp claim follows settings.jwt_access_token_expire_minutes."""
    with patch.object(jwt_service, "settings") as ms:
        ms.jwt_secret = _TEST_JWT_SECRET
        ms.jwt_access_token_expire_minutes = 60
        ms.jwt_refresh_token_expire_days = 7
        before = datetime.now(tz=timezone.utc)
        token = jwt_service.create_access_token(_user())
        after = datetime.now(tz=timezone.utc)

    payload = pyjwt.decode(token, _TEST_JWT_SECRET, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert before + timedelta(minutes=60) - timedelta(seconds=5) <= exp <= after + timedelta(minutes=60)


def test_create_refresh_token_uses_configured_ttl() -> None:
    """Refresh token exp claim follows settings.jwt_refresh_token_expire_days."""
    with patch.object(jwt_service, "settings") as ms:
        ms.jwt_secret = _TEST_JWT_SECRET
        ms.jwt_access_token_expire_minutes = 15
        ms.jwt_refresh_token_expire_days = 30
        before = datetime.now(tz=timezone.utc)
        token = jwt_service.create_refresh_token(_user())
        after = datetime.now(tz=timezone.utc)

    payload = pyjwt.decode(token, _TEST_JWT_SECRET, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert before + timedelta(days=30) - timedelta(seconds=5) <= exp <= after + timedelta(days=30)
