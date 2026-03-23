"""Google OAuth 2.0 service for authorization code exchange and id_token verification."""

import asyncio

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def exchange_code(code: str, code_verifier: str) -> str:
    """Exchange an authorization code + PKCE verifier for a Google id_token.

    POSTs to Google's token endpoint and returns the raw id_token string.
    Raises httpx.HTTPStatusError on a non-2xx response from Google.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()

    token_data = response.json()
    logger.info("google_code_exchanged")
    return token_data["id_token"]


async def verify_id_token(id_token: str) -> dict:
    """Verify a Google id_token and return the decoded payload.

    Uses google-auth to verify the token signature, iss, aud, and exp.
    Returns a dict with at minimum: sub, email, name, picture.
    Raises GoogleAuthError if the token is invalid or expired.
    """

    def _verify() -> dict:
        request = google_requests.Request()
        return google_id_token.verify_oauth2_token(
            id_token,
            request,
            settings.google_client_id,
        )

    try:
        payload: dict = await asyncio.to_thread(_verify)
        logger.info("google_id_token_verified", google_id=payload.get("sub"))
        return payload
    except GoogleAuthError as exc:
        logger.warning("google_id_token_invalid", error=str(exc))
        raise
