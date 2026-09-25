import logging

from app.core import metrics


def test_route_template_uses_low_cardinality_placeholder_for_unmatched() -> None:
    matched = type(
        "RequestStub",
        (),
        {"scope": {"route": type("RouteStub", (), {"path": "/orders/{order_id}"})()}},
    )()
    unmatched = type("RequestStub", (), {"scope": {}})()

    assert metrics.route_template(matched) == "/orders/{order_id}"
    assert metrics.route_template(unmatched) == "unmatched"


def test_status_class() -> None:
    assert metrics.status_class(204) == "2xx"
    assert metrics.status_class(404) == "4xx"
    assert metrics.status_class(503) == "5xx"


def test_configure_metrics_is_callable_without_side_effects() -> None:
    metrics.configure_metrics()


async def test_emit_metrics_writes_one_structured_event(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="metrics"):
        await metrics.emit_metrics(
            [("RequestCount", 1, "Count")],
            {"Method": "GET", "Route": "/orders/{order_id}", "StatusClass": "2xx"},
        )

    assert len(caplog.records) == 1
    payload = vars(caplog.records[0])
    assert payload["event"] == "metric_emitted"
    assert payload["service"] == metrics.SERVICE_NAME
    assert payload["metric_namespace"] == metrics.NAMESPACE
    assert payload["environment"] == "development"
    assert payload["Method"] == "GET"
    assert payload["Route"] == "/orders/{order_id}"
    assert payload["StatusClass"] == "2xx"
    assert payload["RequestCount"] == 1
    assert payload["RequestCount_unit"] == "Count"


async def test_emit_metrics_without_dimensions(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="metrics"):
        await metrics.emit_metrics([("HealthCheckFailure", 1, "Count")])

    assert len(caplog.records) == 1
    payload = vars(caplog.records[0])
    assert payload["HealthCheckFailure"] == 1
    assert payload["HealthCheckFailure_unit"] == "Count"


async def test_emit_metrics_failure_does_not_raise(monkeypatch, caplog) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("stdout unavailable")

    monkeypatch.setattr(metrics, "_metrics_logger", type("_Boom", (), {"info": _boom})())

    with caplog.at_level(logging.ERROR):
        await metrics.emit_metrics([], {})

    assert "failed to emit metrics" in caplog.text


async def test_health_probe_does_not_emit_request_metrics(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="metrics"):
        response = await client.get("/health")

    assert response.status_code == 200
    metric_records = [r for r in caplog.records if r.name == "metrics"]
    assert metric_records == []


async def test_metrics_failure_does_not_break_response(client, monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("stdout unavailable")

    monkeypatch.setattr(metrics, "_metrics_logger", type("_Boom", (), {"info": _boom})())

    response = await client.get("/health")

    assert response.status_code == 200
