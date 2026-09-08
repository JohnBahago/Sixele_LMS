from collections import defaultdict, deque
from time import monotonic
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        if settings.trusted_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
        if request.headers.get("content-length"):
            try:
                if int(request.headers["content-length"]) > settings.max_request_body_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large", "request_id": request.state.request_id})
            except ValueError:
                pass

        key = self._client_key(request)
        now = monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] >= settings.rate_limit_window_seconds:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_requests:
            return JSONResponse(status_code=429, content={"detail": "Too many requests", "request_id": request.state.request_id})
        bucket.append(now)

        try:
            response = await call_next(request)
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request.state.request_id})
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
