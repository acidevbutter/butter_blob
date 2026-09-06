from typing import Annotated

from fastapi import Depends

from app.blobs.repository import BlobRepository
from app.core.dependencies import DbSession
from app.core.storage import BlobStorageDep
from app.public.service import PublicService


def get_public_service(db: DbSession, storage: BlobStorageDep) -> PublicService:
    return PublicService(BlobRepository(db), storage)


PublicServiceDep = Annotated[PublicService, Depends(get_public_service)]
