"""Schema for the running-version endpoint."""

from pydantic import BaseModel


class VersionResponse(BaseModel):
    """The backend release version, e.g. ``0.12.0`` (``dev`` outside released images)."""

    version: str
