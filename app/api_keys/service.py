import hashlib
import secrets
from uuid import UUID

from app.api_keys.models import ApiKey
from app.api_keys.repository import ApiKeyRepository
from app.core.decorators import log_errors
from app.core.exceptions import NotFoundError, UnauthorizedError

_KEY_PREFIX = "bbk_"


@log_errors
class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository):
        self.repository = repository

    @staticmethod
    def _hash(plain: str) -> str:
        return hashlib.sha256(plain.encode()).hexdigest()

    async def create(self, namespace: str, label: str) -> tuple[ApiKey, str]:
        plain = _KEY_PREFIX + secrets.token_urlsafe(32)
        api_key = await self.repository.create(
            ApiKey(namespace=namespace, key_hash=self._hash(plain), prefix=_KEY_PREFIX, label=label)
        )
        return api_key, plain

    async def authenticate(self, plain: str) -> ApiKey:
        api_key = await self.repository.get_by_hash(self._hash(plain))
        if api_key is None or api_key.revoked_at is not None:
            raise UnauthorizedError("Invalid or revoked API key")
        await self.repository.touch_last_used(api_key)
        return api_key

    async def list(self, namespace: str) -> list[ApiKey]:
        return await self.repository.list(namespace)

    async def revoke(self, namespace: str, key_id: UUID) -> ApiKey:
        api_key = await self.repository.get_for_namespace(namespace, key_id)
        if api_key is None:
            raise NotFoundError("API key not found for this namespace")
        return await self.repository.revoke(api_key)
