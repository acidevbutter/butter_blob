from uuid import UUID

from fastapi import APIRouter, status

from app.api_keys.dependencies import ApiKeyServiceDep
from app.api_keys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.core.dependencies import RequireAdminApiKey

router = APIRouter(
    prefix="/admin/v1/namespaces/{slug}/keys",
    tags=["api-keys"],
    dependencies=[RequireAdminApiKey],
)


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(slug: str, service: ApiKeyServiceDep) -> list[ApiKeyRead]:
    return [ApiKeyRead.model_validate(key) for key in await service.list(slug)]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    slug: str, payload: ApiKeyCreate, service: ApiKeyServiceDep
) -> ApiKeyCreated:
    api_key, plaintext_key = await service.create(slug, payload.label)
    return ApiKeyCreated(
        **ApiKeyRead.model_validate(api_key).model_dump(), plaintext_key=plaintext_key
    )


@router.post("/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    slug: str, key_id: UUID, service: ApiKeyServiceDep
) -> ApiKeyRead:
    return ApiKeyRead.model_validate(await service.revoke(slug, key_id))
