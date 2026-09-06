"""Small helpers so the service layer emits metrics in one line and routers stay
metric-free. Everything here delegates to app.core.metrics.emit_metrics, which
already swallows telemetry failures.
"""

from __future__ import annotations

from app.core.metrics import Metric, emit_metrics


async def emit_blob_metric(
    name: str,
    value: float = 1,
    unit: str = "Count",
    *,
    namespace: str | None = None,
    **dimensions: str,
) -> None:
    """Emit one file-level metric. `namespace` (the owning API) is the dimension
    every blob metric carries; extra keyword dimensions (Visibility, Temporary,
    Reason, Mode, ...) are passed straight through.
    """
    dims: dict[str, str] = {}
    if namespace is not None:
        dims["Namespace"] = namespace
    dims.update(dimensions)
    await emit_metrics([(name, value, unit)], dims or None)


async def emit_blob_metrics(
    metrics: list[Metric],
    *,
    namespace: str | None = None,
    **dimensions: str,
) -> None:
    """Emit a batch of file-level metrics sharing the same dimension set."""
    dims: dict[str, str] = {}
    if namespace is not None:
        dims["Namespace"] = namespace
    dims.update(dimensions)
    await emit_metrics(metrics, dims or None)
