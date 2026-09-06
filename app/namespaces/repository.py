from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.db.base import Base
from app.namespaces.models import Namespace


class NamespaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_slug(self, slug: str) -> Namespace | None:
        result = await self.session.execute(select(Namespace).where(Namespace.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, namespace: Namespace) -> Namespace:
        self.session.add(namespace)
        await self._commit_or_raise_conflict(namespace.slug)
        await self.session.refresh(namespace)
        return namespace

    async def upsert(self, slug: str) -> Namespace:
        namespace = await self.get_by_slug(slug)
        if namespace is not None:
            return namespace

        namespace = Namespace(slug=slug)
        self.session.add(namespace)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_slug(slug)
            if existing is not None:
                return existing
            raise
        await self.session.refresh(namespace)
        return namespace

    async def update(self, namespace: Namespace) -> Namespace:
        await self.session.commit()
        await self.session.refresh(namespace)
        return namespace

    async def list_all(self) -> list[Namespace]:
        result = await self.session.execute(select(Namespace).order_by(Namespace.slug))
        return list(result.scalars().all())

    async def usage(self, slug: str) -> tuple[int, int, int]:
        """Return zero usage until the blobs domain has been installed."""
        if "blobs" not in Base.metadata.tables:
            return 0, 0, 0
        try:
            from app.blobs.models import Blob, BlobStatus
        except ImportError:
            return 0, 0, 0

        result = await self.session.execute(
            select(
                func.count(Blob.id),
                func.coalesce(func.sum(Blob.byte_size), 0),
                func.count(Blob.id).filter(Blob.expires_at.is_not(None)),
            ).where(Blob.namespace == slug, Blob.status == BlobStatus.STORED)
        )
        count, total_bytes, temporary_count = result.one()
        return int(count), int(total_bytes), int(temporary_count)

    async def _commit_or_raise_conflict(self, slug: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"A namespace with slug {slug!r} already exists") from exc
