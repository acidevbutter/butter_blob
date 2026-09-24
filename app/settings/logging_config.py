import logging.config

from app.core.metrics import SERVICE_NAME
from app.settings.config import settings
from app.settings.terminal_logging import ServiceContextFilter, TerminalFormatter


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "terminal": {"()": TerminalFormatter},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "terminal",
                    "filters": ["service_context"],
                },
            },
            "filters": {
                "service_context": {
                    "()": ServiceContextFilter,
                    "service_name": SERVICE_NAME,
                    "environment": settings.environment,
                }
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
