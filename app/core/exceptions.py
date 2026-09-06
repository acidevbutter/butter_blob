from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response

Handler = Callable[[Request, Exception], Awaitable[Response]]
_registry: dict[type[Exception], Handler] = {}


def exception_handler(exc_type: type[Exception]) -> Callable[[Handler], Handler]:
    """Decorator that registers a handler function for an exception type.
    Collect all of these onto the app with register_exception_handlers(app).
    """
    def decorator(func: Handler) -> Handler:
        _registry[exc_type] = func
        return func
    return decorator


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, handler in _registry.items():
        app.add_exception_handler(exc_type, handler)


class DomainError(Exception):
    """Base for every error the service layer / repositories are allowed to raise.

    Carries a human-readable `detail`; each subclass maps to one HTTP status via
    a registered handler below. Nothing above the repository should ever see a
    raw SQLAlchemy or botocore exception -- those are translated to one of these.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail: str = "Internal error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Resource not found"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflict"


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Unauthorized"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Forbidden"


class ValidationFailedError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Validation failed"


class UnsupportedMediaTypeError(DomainError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "File format not allowed for this namespace"


class PayloadTooLargeError(DomainError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "File exceeds the allowed size"


class QuotaExceededError(DomainError):
    status_code = status.HTTP_507_INSUFFICIENT_STORAGE
    default_detail = "Namespace storage quota exceeded"


class GoneError(DomainError):
    status_code = status.HTTP_410_GONE
    default_detail = "Resource has expired"


class StorageError(DomainError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Object storage is unavailable"


def _make_handler(exc_type: type[DomainError]) -> Handler:
    async def handler(request: Request, exc: Exception) -> Response:
        detail = getattr(exc, "detail", exc_type.default_detail)
        return JSONResponse(status_code=exc_type.status_code, content={"detail": detail})

    return handler


# Register one handler per concrete DomainError subclass. Adding a new domain
# error is a one-line change: define the class above, add it to this tuple.
for _exc_type in (
    NotFoundError,
    ConflictError,
    UnauthorizedError,
    ForbiddenError,
    ValidationFailedError,
    UnsupportedMediaTypeError,
    PayloadTooLargeError,
    QuotaExceededError,
    GoneError,
    StorageError,
):
    exception_handler(_exc_type)(_make_handler(_exc_type))
