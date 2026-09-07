from fastapi import APIRouter

from app.core.dependencies import CallerNamespace, RequireServiceApiKey
from app.core.exceptions import NotFoundError
from app.namespaces.dependencies import NamespaceServiceDep
from app.namespaces.schemas import NamespaceRead, NamespaceSelfUpdate, NamespaceUsageRead

router = APIRouter(
    prefix="/internal/v1/namespaces", tags=["namespaces"], dependencies=[RequireServiceApiKey]
)


def _require_owner(slug: str, caller: str) -> None:
    if slug != caller:
        raise NotFoundError()


@router.get("/{slug}", response_model=NamespaceUsageRead)
async def get_namespace(
    slug: str, caller: CallerNamespace, service: NamespaceServiceDep
) -> NamespaceUsageRead:
    _require_owner(slug, caller)
    return await service.get_usage(slug)


@router.patch("/{slug}", response_model=NamespaceRead)
async def update_namespace(
    slug: str, payload: NamespaceSelfUpdate, caller: CallerNamespace, service: NamespaceServiceDep
) -> NamespaceRead:
    _require_owner(slug, caller)
    return NamespaceRead.model_validate(await service.update_self(slug, payload))
