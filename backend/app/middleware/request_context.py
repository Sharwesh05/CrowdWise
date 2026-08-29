"""Request-scoped middleware: request id, structured access log, rate limiting."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id and emits one structured log line per request.

    Deliberately logs method, path, status, duration, request id and user id —
    and nothing from the body, so credentials and KYC payloads cannot leak into
    the log stream.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["x-request-id"] = request_id
        if not request.url.path.startswith(("/health", "/docs", "/openapi", "/redoc")):
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
                user_id=getattr(request.state, "user_id", None),
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window in-process rate limiter.

    Sufficient for a single-node deployment and the hackathon demo; a multi-node
    deployment should move this to Redis. Auth endpoints get a much tighter
    budget than the rest of the API.
    """

    _AUTH_PATHS = ("/api/auth/login", "/api/auth/register")

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _limit_for(self, path: str) -> int:
        if path.startswith(self._AUTH_PATHS):
            return settings.rate_limit_auth_per_minute
        return settings.rate_limit_default_per_minute

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path.startswith("/health"):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client = forwarded.split(",")[0].strip()
        key = f"{client}:{request.url.path}"
        limit = self._limit_for(request.url.path)
        now = time.monotonic()

        with self._lock:
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                retry_after = max(1, int(60 - (now - window[0])))
                logger.warning("rate_limited", path=request.url.path, client=client)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests. Please slow down.",
                            "details": {"retry_after_seconds": retry_after},
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)

        return await call_next(request)
