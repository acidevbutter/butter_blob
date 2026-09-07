from typing import Annotated

from fastapi import Depends

from app.blobs.repository import BlobRepository
from app.blobs.service import BlobService
from app.core.dependencies import DbSession
from app.core.storage import BlobStorageDep
from app.namespaces.dependencies import NamespaceServiceDep


def get_blob_service(
    db: DbSession, storage: BlobStorageDep, namespaces: NamespaceServiceDep
) -> BlobService:
    return BlobService(BlobRepository(db), storage, namespaces)


BlobServiceDep = Annotated[BlobService, Depends(get_blob_service)]
