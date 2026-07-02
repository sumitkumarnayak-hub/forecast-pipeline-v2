"""HTTP middleware — correlation IDs and request logging."""
from __future__ import annotations

import logging
import time

from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import new_request_id, request_id_var

logger = logging.getLogger("planning_suite.http")


async def request_context_middleware(request: Request, call_next):
    """Plain ASGI-style middleware (avoids BaseHTTPMiddleware deadlocks on Windows)."""
    rid = request.headers.get("x-request-id") or new_request_id()
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-Id"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise
    finally:
        request_id_var.reset(token)
