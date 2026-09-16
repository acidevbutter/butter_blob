import json
import logging.config
from datetime import UTC, datetime
from typing import Any

# Attributes every stdlib LogRecord carries. Anything else on the record (i.e.
# anything passed via `extra={...}` on a logging call, such as `event`,
# `request_id`, `route`, `status_code`, `duration_ms`) is application context
# and gets merged into the JSON payload as-is.
_RESERVED_RECORD_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object per line.

    `message` is the human-readable text; call sites that want a
    machine-readable event name pass `extra={"event": "...", ...}` (matching
    the convention already used by `app.core.decorators.log_call`) and those
    fields are merged verbatim into the JSON object. Never pass file
    contents, presigned URLs, tokens, or other secrets via `extra` or the
    message itself.
    """

    def format(self, record: logging.LogRecord) -> str:
        if record.name == "metrics":
            # app.core.metrics.emit_metrics already renders a flat, complete
            # JSON payload for New Relic ingestion -- wrapping it as this
            # formatter's own "message" string would nest it inside another
            # JSON object, hiding every metric field from New Relic's
            # top-level-key auto-parsing.
            return record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": f"{__name__}.JsonFormatter"},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "json"},
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
                # uvicorn already attaches its own handler to "uvicorn.access" and
                # logs one line per request there (propagate=False by default).
                # Silence it here instead of duplicating our own structured
                # "request_completed"/"request_failed" event from
                # RequestContextMiddleware: at INFO with propagate=True (the old
                # setting) every request was logged twice -- once by uvicorn's
                # own access-log handler, once again via propagation to root's
                # console handler.
                "uvicorn.access": {"level": "WARNING", "propagate": False},
                "botocore": {"level": "WARNING", "propagate": True},
                "boto3": {"level": "WARNING", "propagate": True},
            },
        }
    )
