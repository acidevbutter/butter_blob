from __future__ import annotations

import builtins
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.blobs.models import Blob, BlobEvent, BlobEventAction, BlobStatus, Visibility
from app.core.exceptions import ConflictError


class BlobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, blob: Blob) -> Blob:
        self.session.add(blob)
        await self._commit_or_raise_conflict("Blob namespace/key or public slug already exists")
        await self.session.refresh(blob)
        return blob

    async def get(self, blob_id: UUID) -> Blob | None:
        return await self.session.get(Blob, blob_id)

    async def get_for_namespace(self, blob_id: UUID, namespace: str) -> Blob | None:
        blob = await self.get(blob_id)
        return blob if blob is not None and blob.namespace == namespace else None

    async def get_public(self, namespace: str, public_slug: str) -> Blob | None:
        result = await self.session.execute(
            select(Blob).where(
                Blob.namespace == namespace,
                Blob.public_slug == public_slug,
                Blob.visibility == Visibility.PUBLIC,
                Blob.status == BlobStatus.STORED,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        namespace: str,
        *,
        visibility: Visibility | None = None,
        status: BlobStatus | None = None,
        checksum: str | None = None,
        temporary: bool | None = None,
        expired: bool | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 100,
    ) -> builtins.list[Blob]:
        query = select(Blob).where(Blob.namespace == namespace)
        if visibility is not None:
            query = query.where(Blob.visibility == visibility)
        if status is not None:
            query = query.where(Blob.status == status)
        if checksum is not None:
            query = query.where(Blob.checksum_sha256 == checksum)
        if temporary is True:
            query = query.where(Blob.expires_at.is_not(None))
        elif temporary is False:
            query = query.where(Blob.expires_at.is_(None))
        if expired is True:
            query = query.where(Blob.expires_at.is_not(None), Blob.expires_at < func.now())
        elif expired is False:
            query = query.where((Blob.expires_at.is_(None)) | (Blob.expires_at >= func.now()))
        if created_after is not None:
            query = query.where(Blob.created_at >= created_after)
        if created_before is not None:
            query = query.where(Blob.created_at <= created_before)
        result = await self.session.execute(query.order_by(Blob.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def update(self, blob: Blob) -> Blob:
        self.session.add(blob)
        await self._commit_or_raise_conflict("Blob namespace/key or public slug already exists")
        await self.session.refresh(blob)
        return blob

    async def soft_delete(self, blob: Blob) -> Blob:
        blob.status = BlobStatus.DELETED
        blob.deleted_at = datetime.now(UTC)
        return await self.update(blob)

    async def hard_delete(self, blob: Blob) -> None:
        await self.session.delete(blob)
        await self.session.commit()

    async def add_event(
        self,
        blob_id: UUID,
        namespace: str,
        action: BlobEventAction,
        detail: dict[str, Any] | None = None,
    ) -> BlobEvent:
        event = BlobEvent(blob_id=blob_id, namespace=namespace, action=action, detail=detail or {})
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_events(self, blob_id: UUID) -> builtins.list[BlobEvent]:
        result = await self.session.execute(
            select(BlobEvent).where(BlobEvent.blob_id == blob_id).order_by(BlobEvent.at.desc())
        )
        return list(result.scalars().all())

    async def sum_stored_bytes(self, namespace: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Blob.byte_size), 0)).where(
                Blob.namespace == namespace, Blob.status == BlobStatus.STORED
            )
        )
        return int(result.scalar_one() or 0)

    async def iter_expired(
        self, before: datetime, namespace: str | None = None, limit: int = 500
    ) -> builtins.list[Blob]:
        query = select(Blob).where(Blob.expires_at.is_not(None), Blob.expires_at < before)
        if namespace is not None:
            query = query.where(Blob.namespace == namespace)
        result = await self.session.execute(query.order_by(Blob.expires_at).limit(limit))
        return list(result.scalars().all())

    async def _commit_or_raise_conflict(self, detail_prefix: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(detail_prefix) from exc
