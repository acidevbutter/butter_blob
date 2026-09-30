import logging
import time
import uuid

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.settings.config import SERVICE_NAME, settings

logger = logging.getLogger("app.request")
_PROBE_PATHS = frozenset({"/health", "/health/ready"})


def _log_route(request: Request) -> str:
    """Route template for the log event, falling back to the actual request
    path for unmatched/404 requests (useful for debugging)."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, emits exactly one structured
    log event per request (success or failure)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request failed",
                extra={
                    "event": "request_failed",
                    "service": SERVICE_NAME,
                    "environment": settings.environment,
                    "request_id": request_id,
                    "method": request.method,
                    "route": _log_route(request),
                    "status_code": 500,
                    "duration_ms": round(duration_ms, 1),
                },
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        if request.url.path in _PROBE_PATHS:
            return response
        logger.info(
            "request completed",
            extra={
                "event": "request_completed",
                "service": SERVICE_NAME,
                "environment": settings.environment,
                "request_id": request_id,
                "method": request.method,
                "route": _log_route(request),
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie_name,
        https_only=settings.environment in {"staging", "preprod", "production"},
    )
