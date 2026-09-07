from __future__ import annotations

from datetime import UTC, datetime

from app.blobs.models import Blob
from app.blobs.repository import BlobRepository
from app.core.decorators import log_errors
from app.core.exceptions import GoneError, NotFoundError
from app.core.observability import emit_blob_metric
from app.core.storage import BlobStorage
from app.public.schemas import PublicMeta
from app.settings.config import settings


@log_errors
class PublicService:
    def __init__(self, repo: BlobRepository, storage: BlobStorage) -> None:
        self.repo = repo
        self.storage = storage

    @staticmethod
    def _is_expired(blob: Blob) -> bool:
        if blob.expires_at is None:
            return False
        expires_at = blob.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)

    async def resolve(self, namespace: str, public_slug: str) -> Blob:
        blob = await self.repo.get_public(namespace, public_slug)
        if blob is None:
            await emit_blob_metric("PublicBlobMiss", namespace=namespace, Reason="not_found")
            raise NotFoundError()
        if self._is_expired(blob):
            await emit_blob_metric("PublicBlobMiss", namespace=namespace, Reason="expired")
            raise GoneError()
        return blob

    async def redirect_url(self, namespace: str, public_slug: str, *, disposition: str) -> str:
        blob = await self.resolve(namespace, public_slug)
        url = await self.storage.generate_presigned_get(
            blob.key,
            min(300, settings.s3_presign_expires_seconds),
            disposition=disposition,
            filename=blob.filename,
        )
        await emit_blob_metric("PublicBlobServed", namespace=namespace)
        return url

    async def meta(self, namespace: str, public_slug: str) -> PublicMeta:
        return PublicMeta.model_validate(await self.resolve(namespace, public_slug))
