from fastapi import APIRouter

from app.blobs.schemas import PurgeResult
from app.core.dependencies import RequireServiceApiKey
from app.maintenance.dependencies import MaintenanceServiceDep

router = APIRouter(
    prefix="/internal/v1/maintenance", tags=["maintenance"], dependencies=[RequireServiceApiKey]
)


@router.post("/purge-expired", response_model=PurgeResult)
async def purge_expired(
    service: MaintenanceServiceDep,
    namespace: str | None = None,
    older_than_seconds: int | None = None,
) -> PurgeResult:
    return await service.purge_expired(
        namespace=namespace, older_than_seconds=older_than_seconds
    )
