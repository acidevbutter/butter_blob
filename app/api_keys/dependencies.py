from typing import Annotated

from fastapi import Depends, Header

from app.api_keys.models import ApiKey
from app.api_keys.repository import ApiKeyRepository
from app.api_keys.service import ApiKeyService
from app.core.dependencies import DbSession
from app.core.exceptions import UnauthorizedError


def get_api_key_service(db: DbSession) -> ApiKeyService:
    return ApiKeyService(ApiKeyRepository(db))


ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]


async def get_current_api_key(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> ApiKey:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")
    plain = authorization.removeprefix("Bearer ").strip()
    if not plain or not plain.startswith("bbk_"):
        raise UnauthorizedError("Missing or malformed Authorization header")
    return await ApiKeyService(ApiKeyRepository(db)).authenticate(plain)


CurrentApiKey = Annotated[ApiKey, Depends(get_current_api_key)]
