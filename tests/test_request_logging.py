import logging

import pytest

from app.settings.terminal_logging import ServiceContextFilter, TerminalFormatter


async def test_health_probe_does_not_emit_a_completion_event(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = await client.get("/health")

    assert response.status_code == 200
    request_records = [r for r in caplog.records if r.name == "app.request"]
    assert request_records == []


async def test_404_request_logs_raw_path_not_a_route_template(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = await client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    request_records = [r for r in caplog.records if r.name == "app.request"]
    assert len(request_records) == 1
    record = request_records[0]
    assert record.event == "request_completed"
    assert record.status_code == 404
    assert record.route == "/this-route-does-not-exist"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_unhandled_exception_logs_exactly_one_failure_event_with_traceback():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.settings.middleware import register_middleware

    app = FastAPI()
    register_middleware(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    transport = ASGITransport(app=app)
    logger = logging.getLogger("app.request")
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            with pytest.raises(RuntimeError, match="kaboom"):
                await ac.get("/boom")
    finally:
        logger.removeHandler(handler)

    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.__dict__["event"] == "request_failed"
    assert record.__dict__["status_code"] == 500
    assert record.exc_info is not None
    # message stays generic; the traceback (via exc_info) carries the detail
    assert "kaboom" not in record.getMessage()


def test_terminal_formatter_renders_readable_structured_fields():
    logger_name = "app.request"
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.event = "request_completed"
    ServiceContextFilter("butter-blob", "development").filter(record)
    record.request_id = "abc-123"
    record.method = "GET"
    record.route = "/health"
    record.status_code = 200
    record.duration_ms = 1.2

    line = TerminalFormatter().format(record)

    assert "[butter-blob/development]" in line
    assert "request_completed: request completed" in line
    assert "GET /health | → 200 | 1.2ms | request_id=abc-123" in line


def test_terminal_formatter_keeps_metric_fields_readable():
    record = logging.LogRecord(
        name="metrics",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="metric emitted",
        args=(),
        exc_info=None,
    )

    record.event = "metric_emitted"
    record.log_type = "metric"
    record.Route = "/health"
    ServiceContextFilter("butter-blob", "development").filter(record)

    formatted = TerminalFormatter().format(record)

    assert "[butter-blob/development]" in formatted
    assert "metric_emitted: metric emitted" in formatted


def test_uvicorn_access_logger_is_quiet_and_does_not_propagate():
    from app.settings.logging_config import setup_logging

    setup_logging("INFO")
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.level == logging.WARNING
    assert access_logger.propagate is False
