from typing import Annotated

from fastapi import Depends

from app.blobs.repository import BlobRepository
from app.core.dependencies import DbSession
from app.core.storage import BlobStorageDep
from app.maintenance.service import MaintenanceService


def get_maintenance_service(db: DbSession, storage: BlobStorageDep) -> MaintenanceService:
    return MaintenanceService(BlobRepository(db), storage)


MaintenanceServiceDep = Annotated[MaintenanceService, Depends(get_maintenance_service)]
