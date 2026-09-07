"""Cross-domain dependency-injection providers.

Only providers that every domain needs and none of them own live here: the DB
session, the two API-key guards, and the caller-namespace resolver. Domain-
specific providers (e.g. BlobServiceDep) are defined in that domain's own
router.py / dependencies.py.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from app.core.observability import emit_blob_metric
from app.db.session import get_db_session
from app.namespaces.repository import NamespaceRepository
from app.namespaces.service import NamespaceService
from app.settings.config import settings

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
_caller_api_key_id: ContextVar[UUID | None] = ContextVar("caller_api_key_id", default=None)


@dataclass(frozen=True)
class CallerContextValue:
    namespace: str
    api_key_id: UUID | None


async def require_service_api_key(
    x_service_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Gate for /internal/v1/*. Fails closed as 404 (not 401) so the internal API
    surface is invisible to a caller without the shared secret.
    """
    if authorization is not None and authorization.startswith("Bearer bbk_"):
        return
    if not settings.service_api_key or x_service_api_key != settings.service_api_key:
        await emit_blob_metric("AuthFailure", Reason="service_api_key")
        raise NotFoundError()


async def require_admin_api_key(
    x_admin_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Gate for /admin/v1/*. Same fail-closed-404 behaviour as the service key."""
    if not settings.admin_api_key or x_admin_api_key != settings.admin_api_key:
        await emit_blob_metric("AuthFailure", Reason="admin_api_key")
        raise NotFoundError()


RequireServiceApiKey = Depends(require_service_api_key)
RequireAdminApiKey = Depends(require_admin_api_key)


def normalize_namespace(raw: str) -> str:
    """Lowercase + strip to the ``[a-z0-9_-]`` charset so ``Crate Diggr`` and
    ``crate_diggr`` and ``crate-diggr`` don't become three different owners.
    """
    return slugify(raw, lowercase=True, regex_pattern=r"[^a-z0-9_-]+").strip("-_")


async def get_caller_context(
    db: DbSession,
    x_blob_namespace: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AsyncGenerator[CallerContextValue, None]:
    """Resolve an internal caller from a bearer key or the legacy headers."""
    api_key_id: UUID | None = None
    if authorization is not None and authorization.startswith("Bearer bbk_"):
        from app.api_keys.repository import ApiKeyRepository
        from app.api_keys.service import ApiKeyService

        api_key = await ApiKeyService(ApiKeyRepository(db)).authenticate(
            authorization.removeprefix("Bearer ").strip()
        )
        namespace = api_key.namespace
        api_key_id = api_key.id
        if x_blob_namespace is not None and x_blob_namespace.strip():
            declared_namespace = normalize_namespace(x_blob_namespace)
            if declared_namespace != namespace:
                raise ForbiddenError("X-Blob-Namespace does not match the bearer key")
    else:
        if not settings.allow_header_namespace:
            raise NotFoundError()
        if x_blob_namespace is None or not x_blob_namespace.strip():
            raise ValidationFailedError("Missing X-Blob-Namespace header")
        namespace = normalize_namespace(x_blob_namespace)
        if not namespace:
            raise ValidationFailedError("X-Blob-Namespace is empty after normalization")

    resolved = await NamespaceService(NamespaceRepository(db)).resolve_caller(namespace)
    token = _caller_api_key_id.set(api_key_id)
    try:
        yield CallerContextValue(namespace=resolved.slug, api_key_id=api_key_id)
    finally:
        _caller_api_key_id.reset(token)


CallerContext = Annotated[CallerContextValue, Depends(get_caller_context)]


async def get_caller_namespace(caller: CallerContext) -> str:
    return caller.namespace


def get_current_api_key_id() -> UUID | None:
    """Bearer key ID for the active request, used only for audit detail."""
    return _caller_api_key_id.get()


CallerNamespace = Annotated[str, Depends(get_caller_namespace)]
