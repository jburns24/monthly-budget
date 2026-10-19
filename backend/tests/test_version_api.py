"""GET /api/version reports the configured release version without auth."""

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from app.config import Settings, settings
from app.main import app


async def _get_version() -> tuple[int, dict]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/version")
    return response.status_code, response.json()


async def test_version_is_public_and_reports_app_version(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_version", "0.12.0")

    status_code, body = await _get_version()

    assert status_code == 200
    assert body == {"version": "0.12.0"}


async def test_version_defaults_to_dev() -> None:
    assert Settings.model_fields["app_version"].default == "dev"


def test_app_version_reads_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.3")

    assert Settings().app_version == "1.2.3"
