"""New Relic structured JSON metrics helpers for Butter Blob.

Replaces the previous CloudWatch Embedded Metric Format (EMF) sink
(``aws_embedded_metrics``). Metrics are written as a single JSON line via the
standard `logging` module instead of the EMF wire format: the same ECS
`awslogs` -> CloudWatch Logs pipeline this service already ships stdout
through forwards to New Relic's log ingestion, which auto-parses JSON log
lines and promotes their top-level keys to queryable log attributes -- no
agent, no new dependency.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence

from starlette.requests import Request

from app.settings.config import settings

logger = logging.getLogger(__name__)
_metrics_logger = logging.getLogger("metrics")

NAMESPACE = "DevButter/ButterBlob"
SERVICE_NAME = "butter-blob"

Metric = tuple[str, float, str]


def configure_metrics() -> None:
    """No-op retained for main.py's startup call. EMF needed a get_config()
    singleton configured before the first emit; the New Relic JSON sink
    below (see emit_metrics) carries no equivalent global state, so there is
    nothing left to configure here.
    """


def route_template(request: Request) -> str:
    """Return the low-cardinality route template, never a raw path with IDs."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


async def emit_metrics(
    metrics: Sequence[Metric], dimensions: Mapping[str, str] | None = None
) -> None:
    """Write one metric log line without allowing telemetry failures to affect work."""
    try:
        payload: dict[str, object] = {
            "timestamp": int(time.time() * 1000),
            "message": "metric_emitted",
            "service.name": SERVICE_NAME,
            "environment": settings.environment,
            "metric.namespace": NAMESPACE,
            **(dimensions or {}),
        }
        for name, value, unit in metrics:
            payload[name] = value
            payload[f"{name}.unit"] = unit
        _metrics_logger.info(json.dumps(payload, default=str))
    except Exception:
        logger.exception("failed to emit metrics")
