from fastapi import APIRouter, status

from app.core.dependencies import RequireAdminApiKey
from app.namespaces.dependencies import NamespaceServiceDep
from app.namespaces.schemas import (
    NamespaceCreate,
    NamespaceLimitsUpdate,
    NamespaceRead,
    NamespaceUsageRead,
)

router = APIRouter(prefix="/admin/v1", tags=["admin"], dependencies=[RequireAdminApiKey])


@router.get("/namespaces", response_model=list[NamespaceUsageRead])
async def list_namespaces(service: NamespaceServiceDep) -> list[NamespaceUsageRead]:
    return await service.list_with_usage()


@router.get("/namespaces/{slug}", response_model=NamespaceUsageRead)
async def get_namespace(slug: str, service: NamespaceServiceDep) -> NamespaceUsageRead:
    return await service.get_usage(slug)


@router.post("/namespaces", response_model=NamespaceRead, status_code=status.HTTP_201_CREATED)
async def create_namespace(payload: NamespaceCreate, service: NamespaceServiceDep) -> NamespaceRead:
    return NamespaceRead.model_validate(await service.create(payload))


@router.put("/namespaces/{slug}/limits", response_model=NamespaceRead)
async def set_namespace_limits(
    slug: str, payload: NamespaceLimitsUpdate, service: NamespaceServiceDep
) -> NamespaceRead:
    return NamespaceRead.model_validate(await service.set_limits(slug, payload))
