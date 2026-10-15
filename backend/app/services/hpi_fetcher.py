"""Downloads of the FHFA house price index files."""

from importlib import metadata
from typing import Protocol

import httpx

from app.services.assets.hpi_import import STATE_URL, ZIP3_URL

_TIMEOUT_SECONDS = 60.0


class HpiFetcher(Protocol):
    """Where the raw index files come from; tests substitute a fake that never touches the network."""

    async def fetch_zip3_xlsx(self) -> bytes:
        """The three-digit ZIP workbook, as bytes."""
        ...

    async def fetch_state_csv(self) -> str:
        """The state CSV, as text."""
        ...


def _user_agent() -> str:
    try:
        version = metadata.version("monthly-budget-backend")
    except metadata.PackageNotFoundError:
        version = "0.0.0"
    return f"monthly-budget/{version} (+self-hosted household budget app)"


class HttpxHpiFetcher:
    """Downloads the files from fhfa.gov."""

    def __init__(self, zip3_url: str = ZIP3_URL, state_url: str = STATE_URL) -> None:
        self._zip3_url = zip3_url
        self._state_url = state_url

    async def _get(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, headers={"User-Agent": _user_agent()}, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response

    async def fetch_zip3_xlsx(self) -> bytes:
        return (await self._get(self._zip3_url)).content

    async def fetch_state_csv(self) -> str:
        return (await self._get(self._state_url)).text
