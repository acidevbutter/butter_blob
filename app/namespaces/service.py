from app.core.decorators import log_errors
from app.core.exceptions import NotFoundError
from app.namespaces.models import Namespace
from app.namespaces.repository import NamespaceRepository
from app.namespaces.schemas import (
    NamespaceCreate,
    NamespaceLimitsUpdate,
    NamespaceRead,
    NamespaceSelfUpdate,
    NamespaceUsageRead,
)


@log_errors
class NamespaceService:
    def __init__(self, repository: NamespaceRepository):
        self.repository = repository

    async def resolve_caller(self, slug: str) -> Namespace:
        return await self.repository.upsert(slug)

    async def get(self, slug: str) -> Namespace:
        namespace = await self.repository.get_by_slug(slug)
        if namespace is None:
            raise NotFoundError(f"Namespace {slug!r} not found")
        return namespace

    async def get_usage(self, slug: str) -> NamespaceUsageRead:
        namespace = await self.get(slug)
        blob_count, total_bytes, temporary_count = await self.repository.usage(slug)
        data = NamespaceRead.model_validate(namespace).model_dump()
        return NamespaceUsageRead(
            **data,
            blob_count=blob_count,
            total_bytes=total_bytes,
            temporary_count=temporary_count,
        )

    async def list_with_usage(self) -> list[NamespaceUsageRead]:
        namespaces = await self.repository.list_all()
        return [await self.get_usage(namespace.slug) for namespace in namespaces]

    async def create(self, payload: NamespaceCreate) -> Namespace:
        values = payload.model_dump()
        return await self.repository.create(Namespace(**values))

    async def set_limits(self, slug: str, payload: NamespaceLimitsUpdate) -> Namespace:
        namespace = await self.get(slug)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(namespace, field, value)
        return await self.repository.update(namespace)

    async def update_self(self, slug: str, payload: NamespaceSelfUpdate) -> Namespace:
        namespace = await self.get(slug)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(namespace, field, value)
        return await self.repository.update(namespace)
