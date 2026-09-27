import json
import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("qems.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter applied only to auth and evidence-upload paths (Section 14.7)."""

    def __init__(self, app, limited_prefixes: tuple[str, ...], limit_per_minute: int):
        super().__init__(app)
        self.limited_prefixes = limited_prefixes
        self.limit_per_minute = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.limited_prefixes):
            host = request.client.host if request.client else "unknown"
            key = f"{host}:{path}"

            # Finding D-05: this bucket was IP+path only, so every account behind one
            # NAT/shared-IP shared a single 5/min login budget -- one noisy or malicious
            # client could lock out every other user on that network. For the login path
            # specifically, fold the submitted email into the key too, so distinct
            # accounts get independent budgets; a single account is still capped
            # regardless of which IP it's hammered from. The body has to be read here
            # and then replayed for the downstream handler (FastAPI's own body parsing),
            # since a Starlette Request only lets its body be consumed once per receive
            # channel.
            if path == "/api/v1/auth/login":
                body = await request.body()

                async def _replay(_body: bytes = body):
                    return {"type": "http.request", "body": _body, "more_body": False}

                request._receive = _replay
                try:
                    email = json.loads(body or b"{}").get("email")
                except (ValueError, AttributeError):
                    email = None
                if email:
                    key = f"{key}:{email}"

            now = time.monotonic()
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.limit_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limited", "message": "Too many requests, slow down."}},
                )
            window.append(now)
        return await call_next(request)
