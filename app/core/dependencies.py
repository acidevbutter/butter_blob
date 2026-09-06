"""Cross-domain dependency-injection providers.

Only providers that every domain needs and none of them own live here: the DB
session, the two API-key guards, and the caller-namespace resolver. Domain-
specific providers (e.g. BlobServiceDep) are defined in that domain's own
router.py / dependencies.py.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.observability import emit_blob_metric
from app.db.session import get_db_session
from app.settings.config import settings

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def require_service_api_key(
    x_service_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Gate for /internal/v1/*. Fails closed as 404 (not 401) so the internal API
    surface is invisible to a caller without the shared secret.
    """
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


async def get_caller_namespace(
    x_blob_namespace: Annotated[str | None, Header()] = None,
) -> str:
    """Identity of the API calling /internal/v1/*. Every blob is bound to this
    value and cross-namespace access 404s.

    Prompt 04 replaces the body with a call to NamespaceService.resolve_caller
    (which also upserts the ``namespaces`` row); until then it just normalizes
    and returns the header.
    """
    if x_blob_namespace is None or not x_blob_namespace.strip():
        raise ValidationFailedError("Missing X-Blob-Namespace header")
    namespace = normalize_namespace(x_blob_namespace)
    if not namespace:
        raise ValidationFailedError("X-Blob-Namespace is empty after normalization")
    return namespace


CallerNamespace = Annotated[str, Depends(get_caller_namespace)]
