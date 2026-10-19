"""Public endpoint reporting the running backend release version."""

from fastapi import APIRouter

from app.config import settings
from app.schemas.version import VersionResponse

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Return the release version baked into the image (``APP_VERSION``), or ``dev``.

    Public on purpose: it carries no user data, and the frontend footer shows it.
    """
    return VersionResponse(version=settings.app_version)
