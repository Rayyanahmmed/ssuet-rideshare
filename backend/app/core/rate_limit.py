"""Rate limiting for sensitive endpoints (§19, §22).

SlowAPI keyed on the client IP. Disabled in tests via `RATE_LIMIT_ENABLED=false`,
enabled everywhere else. Every limit is per-endpoint and documented in Swagger.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
    headers_enabled=False,
    default_limits=[],
)


async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return the same error envelope the rest of the API uses."""
    limit = getattr(exc, "detail", None) or "Too many requests."
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many attempts. Please wait a moment and try again.",
                "details": {"limit": str(limit)},
            }
        },
    )
