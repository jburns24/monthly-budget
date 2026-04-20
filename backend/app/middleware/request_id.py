"""RequestIDMiddleware: reads or generates X-Request-ID, binds to structlog, echoes on response."""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Reads X-Request-ID from incoming request or generates a UUID4.

    Binds the value to structlog contextvars so all log events within the
    request include `request_id`. Echoes the value on the response header.
    Clears contextvars after the response is sent.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["X-Request-ID"] = request_id
        return response
