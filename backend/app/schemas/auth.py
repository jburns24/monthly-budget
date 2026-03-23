"""Auth request/response Pydantic schemas."""

from pydantic import BaseModel


class LoginCallbackRequest(BaseModel):
    """Body for POST /api/auth/callback."""

    code: str
    code_verifier: str


class LoginCallbackResponse(BaseModel):
    """Response body for POST /api/auth/callback."""

    is_new_user: bool


class TokenError(BaseModel):
    """Error response for auth failures."""

    detail: str
