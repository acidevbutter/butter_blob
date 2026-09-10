import logging
import time
import uuid

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import SERVICE_NAME, emit_metrics, route_template, status_class
from app.settings.config import settings

logger = logging.getLogger("app.request")


def _log_route(request: Request) -> str:
    """Route template for the log event.

    Unlike `route_template` (used for the low-cardinality EMF `Route`
    dimension, which must never carry a raw path), the log field falls back
    to the actual request path for unmatched/404 requests -- useful for
    debugging, and safe because log fields aren't metric dimensions.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, emits exactly one structured
    JSON log event per request (success or failure), and emits request-level
    EMF metrics (RequestCount, Latency, 4xx/5xxCount)."""

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
        metrics = [
            ("RequestCount", 1, "Count"),
            ("Latency", duration_ms, "Milliseconds"),
        ]
        if response.status_code >= 500:
            metrics.append(("5xxCount", 1, "Count"))
        elif response.status_code >= 400:
            metrics.append(("4xxCount", 1, "Count"))
        await emit_metrics(
            metrics,
            {
                "Method": request.method,
                "Route": route_template(request),
                "StatusClass": status_class(response.status_code),
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
