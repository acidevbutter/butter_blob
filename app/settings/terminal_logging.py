"""Common human-readable stdout format for New Relic log ingestion."""

import json
import logging
from datetime import UTC, datetime

_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _value(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char.isspace() for char in text) else text


class ServiceContextFilter(logging.Filter):
    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service_name = self.service_name
        record.deployment_environment = self.environment
        return True


class TerminalFormatter(logging.Formatter):
    """One readable logfmt line with the New Relic attribute contract."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", "metric_emitted" if record.name == "metrics" else "log")
        log_type = getattr(record, "log_type", None)
        if log_type is None:
            log_type = "metric" if record.name == "metrics" else "error" if record.levelno >= logging.ERROR else "access" if record.name == "app.request" else "application"
        fields: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "service.name": getattr(record, "service_name", "unknown"),
            "deployment.environment": getattr(record, "deployment_environment", "unknown"),
            "log.severity": record.levelname,
            "event.name": event,
            "log.type": log_type,
            "logger": record.name,
            "message": record.getMessage(),
        }
        mapping = {
            "method": "http.request.method",
            "route": "url.path",
            "status_code": "http.response.status_code",
            "request_id": "request.id",
        }
        for source, target in mapping.items():
            if hasattr(record, source):
                fields[target] = getattr(record, source)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in fields and key not in mapping and key not in {"event", "log_type", "service_name", "deployment_environment"}:
                fields[key] = value
        line = " ".join(f"{key}={_value(value)}" for key, value in fields.items())
        return f"{line}\n{self.formatException(record.exc_info)}" if record.exc_info else line
