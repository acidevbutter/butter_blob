from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession
from app.namespaces.repository import NamespaceRepository
from app.namespaces.service import NamespaceService


def get_namespace_service(db: DbSession) -> NamespaceService:
    return NamespaceService(NamespaceRepository(db))


NamespaceServiceDep = Annotated[NamespaceService, Depends(get_namespace_service)]
