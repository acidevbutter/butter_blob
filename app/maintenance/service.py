import logging
from datetime import UTC, datetime, timedelta

from app.blobs.models import BlobEventAction, BlobStatus
from app.blobs.repository import BlobRepository
from app.blobs.schemas import PurgeResult
from app.core.decorators import log_errors
from app.core.exceptions import StorageError
from app.core.storage import BlobStorage

logger = logging.getLogger(__name__)


@log_errors
class MaintenanceService:
    def __init__(self, repo: BlobRepository, storage: BlobStorage) -> None:
        self.repo = repo
        self.storage = storage

    async def purge_expired(
        self, *, namespace: str | None, older_than_seconds: int | None
    ) -> PurgeResult:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds or 0)
        scanned = purged = bytes_reclaimed = 0
        while blobs := await self.repo.iter_expired(cutoff, namespace=namespace):
            scanned += len(blobs)
            for blob in blobs:
                try:
                    await self.storage.delete_object(blob.key)
                except StorageError:
                    logger.warning("Could not delete expired object %s", blob.key, exc_info=True)
                await self.repo.add_event(
                    blob.id, blob.namespace, BlobEventAction.EXPIRED, {"key": blob.key}
                )
                if blob.status == BlobStatus.STORED and blob.byte_size is not None:
                    bytes_reclaimed += blob.byte_size
                await self.repo.hard_delete(blob)
                purged += 1
        return PurgeResult(scanned=scanned, purged=purged, bytes_reclaimed=bytes_reclaimed)
