from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from builtins import list as builtins_list
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.blobs.models import Blob, BlobEvent, BlobEventAction, BlobStatus, Visibility
from app.blobs.repository import BlobRepository
from app.blobs.schemas import BlobPatch, BlobRead, PresignRequest
from app.core import imaging
from app.core.decorators import log_errors
from app.core.exceptions import (
    ConflictError,
    GoneError,
    NotFoundError,
    PayloadTooLargeError,
    QuotaExceededError,
    StorageError,
    UnsupportedMediaTypeError,
    ValidationFailedError,
)
from app.core.jobs import enqueue
from app.core.observability import emit_blob_metric
from app.core.storage import BlobStorage
from app.namespaces.models import Namespace
from app.namespaces.service import NamespaceService
from app.settings.config import settings

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")
logger = logging.getLogger(__name__)


@log_errors
class BlobService:
    def __init__(
        self, repo: BlobRepository, storage: BlobStorage, namespaces: NamespaceService
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.namespaces = namespaces

    @staticmethod
    def _sanitize_filename(name: str | None) -> str:
        basename = os.path.basename(name or "")
        sanitized = _SAFE_FILENAME.sub("", basename)[:200]
        return sanitized or "file"

    @staticmethod
    def _key(namespace: str, blob_id: UUID, filename: str, *, temporary: bool) -> str:
        prefix = "tmp" if temporary else "blobs"
        return f"{prefix}/{namespace}/{blob_id}/{filename}"

    async def _effective_limits(self, namespace: str) -> Namespace:
        return await self.namespaces.get(namespace)

    async def _enforce(
        self,
        ns_limits: Namespace,
        *,
        content_type: str,
        filename: str,
        size: int | None,
        ttl_seconds: int | None,
    ) -> None:
        content_type = content_type.lower()
        extension = os.path.splitext(filename)[1].lower()
        if (
            ns_limits.allowed_content_types is not None
            and content_type not in ns_limits.allowed_content_types
        ) or (
            ns_limits.allowed_extensions is not None
            and extension not in ns_limits.allowed_extensions
        ):
            await emit_blob_metric("UploadRejectedFormat", namespace=ns_limits.slug)
            raise UnsupportedMediaTypeError()

        if size is not None:
            max_file_bytes = (
                ns_limits.max_file_bytes
                if ns_limits.max_file_bytes is not None
                else settings.max_upload_bytes
            )
            if size > max_file_bytes:
                await emit_blob_metric("UploadRejectedTooLarge", namespace=ns_limits.slug)
                raise PayloadTooLargeError()
            if ns_limits.max_storage_bytes is not None:
                used = await self.repo.sum_stored_bytes(ns_limits.slug)
                if used + size > ns_limits.max_storage_bytes:
                    await emit_blob_metric("UploadRejectedQuota", namespace=ns_limits.slug)
                    raise QuotaExceededError()

        if ttl_seconds is not None and ttl_seconds > settings.max_temporary_ttl_seconds:
            await emit_blob_metric("TtlRejected", namespace=ns_limits.slug)
            raise ValidationFailedError("Temporary TTL exceeds the allowed maximum")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValidationFailedError("Temporary TTL must be greater than zero")

    @staticmethod
    def _resolve_expiry(ttl_seconds: int | None, temporary: bool) -> datetime | None:
        if ttl_seconds is not None:
            return datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        if temporary:
            return datetime.now(UTC) + timedelta(seconds=settings.default_temporary_ttl_seconds)
        return None

    @staticmethod
    def _job_kinds(blob: Blob) -> list[str]:
        """Return the enabled post-processing steps for a stored blob."""
        kinds: list[str] = []
        if settings.clamav_host:
            kinds.append("virus_scan")
        if blob.content_type.startswith("image/") and settings.thumbnail_widths:
            kinds.append("image_thumbnail")
        if blob.content_type.startswith("video/") and settings.enable_video_transcode:
            kinds.append("video_transcode")
        return kinds

    async def _enqueue_processing(self, blob: Blob) -> Blob:
        kinds = self._job_kinds(blob)
        if not kinds:
            return blob
        blob.status = BlobStatus.PROCESSING
        blob = await self.repo.update(blob)
        await self.repo.add_event(
            blob.id, blob.namespace, BlobEventAction.PROCESSING, {"kinds": kinds}
        )
        await enqueue({"blob_id": str(blob.id), "namespace": blob.namespace, "kinds": kinds})
        return blob

    def as_read(self, blob: Blob) -> BlobRead:
        response = BlobRead.model_validate(blob)
        if blob.visibility == Visibility.PUBLIC and blob.public_slug:
            response.public_url = (
                f"{settings.public_base_url.rstrip('/')}/v1/public/"
                f"{blob.namespace}/{blob.public_slug}"
            )
        return response

    @staticmethod
    def _is_expired(blob: Blob) -> bool:
        if blob.expires_at is None:
            return False
        expires_at = blob.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)

    async def list(self, namespace: str, **filters: Any) -> list[Blob]:
        return await self.repo.list(namespace, **filters)

    async def get(self, namespace: str, blob_id: UUID, *, allow_expired: bool = False) -> Blob:
        blob = await self.repo.get_for_namespace(blob_id, namespace)
        if blob is None or blob.status == BlobStatus.DELETED:
            raise NotFoundError()
        if not allow_expired and self._is_expired(blob):
            await emit_blob_metric("ExpiredBlobRequested", namespace=namespace)
            raise GoneError()
        return blob

    async def download_url(
        self, namespace: str, blob_id: UUID, *, expires_in: int | None, disposition: str
    ) -> tuple[str, datetime]:
        blob = await self.get(namespace, blob_id)
        if blob.status != BlobStatus.STORED:
            raise NotFoundError()
        expires = min(
            expires_in or settings.s3_presign_expires_seconds, settings.s3_presign_expires_seconds
        )
        url = await self.storage.generate_presigned_get(
            blob.key, expires, disposition=disposition, filename=blob.filename
        )
        await self.repo.add_event(blob.id, namespace, BlobEventAction.DOWNLOADED)
        await emit_blob_metric(
            "BlobDownloadUrlIssued",
            namespace=namespace,
            Visibility=Visibility(blob.visibility).value,
        )
        return url, datetime.now(UTC) + timedelta(seconds=expires)

    async def list_events(self, namespace: str, blob_id: UUID) -> builtins_list[BlobEvent]:
        blob = await self.get(namespace, blob_id)
        return await self.repo.list_events(blob.id)

    async def patch(self, namespace: str, blob_id: UUID, payload: BlobPatch) -> Blob:
        blob = await self.get(namespace, blob_id)
        visibility_changed = (
            payload.visibility is not None and payload.visibility != blob.visibility
        )
        previous_visibility = Visibility(blob.visibility)

        if payload.filename is not None:
            blob.filename = self._sanitize_filename(payload.filename)
        if payload.metadata is not None:
            blob.blob_metadata = {**blob.blob_metadata, **payload.metadata}
        if "expires_at" in payload.model_fields_set:
            if payload.expires_at is None:
                blob.expires_at = None
            else:
                expires_at = payload.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                max_expires_at = datetime.now(UTC) + timedelta(
                    seconds=settings.max_temporary_ttl_seconds
                )
                if expires_at > max_expires_at:
                    raise ValidationFailedError("Temporary TTL exceeds the allowed maximum")
                blob.expires_at = expires_at
        if payload.visibility is not None:
            blob.visibility = payload.visibility
            if blob.visibility == Visibility.PUBLIC and blob.public_slug is None:
                for attempt in range(3):
                    blob.public_slug = secrets.token_urlsafe(12).lower()
                    try:
                        blob.updated_by_namespace = namespace
                        blob = await self.repo.update(blob)
                    except ConflictError:
                        if attempt == 2:
                            raise
                    else:
                        break
                else:  # pragma: no cover - loop either returns or raises
                    raise ConflictError("Could not allocate a public slug")
                # The successful update above persists every patch field.
                await self.repo.add_event(blob.id, namespace, BlobEventAction.UPDATED)
                if visibility_changed:
                    await self.repo.add_event(
                        blob.id,
                        namespace,
                        BlobEventAction.VISIBILITY_CHANGED,
                        {
                            "from": previous_visibility.value,
                            "to": Visibility(blob.visibility).value,
                        },
                    )
                    await emit_blob_metric(
                        "BlobVisibilityChanged",
                        namespace=namespace,
                        To=Visibility(blob.visibility).value,
                    )
                await emit_blob_metric("BlobUpdated", namespace=namespace)
                return blob

        blob.updated_by_namespace = namespace
        blob = await self.repo.update(blob)
        await self.repo.add_event(blob.id, namespace, BlobEventAction.UPDATED)
        if visibility_changed:
            await self.repo.add_event(
                blob.id,
                namespace,
                BlobEventAction.VISIBILITY_CHANGED,
                {"from": previous_visibility.value, "to": Visibility(blob.visibility).value},
            )
            await emit_blob_metric(
                "BlobVisibilityChanged", namespace=namespace, To=Visibility(blob.visibility).value
            )
        await emit_blob_metric("BlobUpdated", namespace=namespace)
        return blob

    async def delete(self, namespace: str, blob_id: UUID, *, hard: bool) -> None:
        blob = await self.get(namespace, blob_id, allow_expired=True)
        try:
            await self.storage.delete_object(blob.key)
        except StorageError:
            if hard:
                raise
            logger.warning(
                "Unable to delete object for soft-deleted blob %s", blob.id, exc_info=True
            )

        mode = "hard" if hard else "soft"
        await self.repo.add_event(blob.id, namespace, BlobEventAction.DELETED, {"mode": mode})
        if hard:
            await self.repo.hard_delete(blob)
        else:
            await self.repo.soft_delete(blob)
        await emit_blob_metric("BlobDeleted", namespace=namespace, Mode=mode)
        if blob.status == BlobStatus.STORED and blob.byte_size is not None:
            await emit_blob_metric("BlobDeletedBytes", blob.byte_size, "Bytes", namespace=namespace)

    async def _read_limited(self, upload: UploadFile) -> bytes:
        cap = settings.max_upload_bytes + 1
        chunks: list[bytes] = []
        total = 0
        while total < cap:
            chunk = await upload.read(min(1024 * 1024, cap - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    async def _emit_compression(self, namespace: str, original_size: int, size: int) -> None:
        await emit_blob_metric("ImageCompressed", namespace=namespace)
        await emit_blob_metric(
            "CompressionBytesSaved", original_size - size, "Bytes", namespace=namespace
        )

    async def upload_proxy(
        self,
        namespace: str,
        *,
        upload: UploadFile,
        visibility: Visibility,
        filename: str | None,
        metadata: dict[str, Any],
        ttl_seconds: int | None,
        temporary: bool = False,
    ) -> Blob:
        started = time.perf_counter()
        name = self._sanitize_filename(filename or upload.filename)
        content_type = (upload.content_type or "application/octet-stream").lower()
        data = await self._read_limited(upload)
        limits = await self._effective_limits(namespace)
        await self._enforce(
            limits,
            content_type=content_type,
            filename=name,
            size=len(data),
            ttl_seconds=ttl_seconds,
        )

        original_size: int | None = None
        if content_type.startswith("image/") and (
            limits.image_compression_quality is not None or limits.image_max_dimension is not None
        ):
            original_size = len(data)
            data, content_type = imaging.transform(
                data,
                content_type,
                quality=limits.image_compression_quality,
                max_dimension=limits.image_max_dimension,
            )
            if content_type == "image/webp":
                name = f"{os.path.splitext(name)[0]}.webp"

        expires_at = self._resolve_expiry(ttl_seconds, temporary)
        blob = Blob(
            id=uuid4(),
            namespace=namespace,
            key="",
            filename=name,
            content_type=content_type,
            byte_size=len(data),
            original_byte_size=original_size,
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            visibility=visibility,
            status=BlobStatus.STORED,
            expires_at=expires_at,
            blob_metadata=metadata,
            created_by_namespace=namespace,
        )
        blob.key = self._key(namespace, blob.id, name, temporary=blob.is_temporary)
        await self.storage.put_object(blob.key, data, content_type)
        blob = await self.repo.create(blob)
        await self.repo.add_event(blob.id, namespace, BlobEventAction.CREATED)
        await self.repo.add_event(blob.id, namespace, BlobEventAction.UPLOADED)
        await emit_blob_metric(
            "BlobCreated",
            namespace=namespace,
            Visibility=visibility.value,
            Temporary=str(blob.is_temporary).lower(),
        )
        await emit_blob_metric(
            "BlobUploadedBytes",
            len(data),
            "Bytes",
            namespace=namespace,
            Temporary=str(blob.is_temporary).lower(),
        )
        if original_size is not None:
            await self._emit_compression(namespace, original_size, len(data))
        await emit_blob_metric(
            "BlobProxyUploadLatency",
            (time.perf_counter() - started) * 1000,
            "Milliseconds",
            namespace=namespace,
        )
        return await self._enqueue_processing(blob)

    async def create_presign(
        self, namespace: str, payload: PresignRequest
    ) -> tuple[Blob, str, datetime]:
        name = self._sanitize_filename(payload.filename)
        content_type = payload.content_type.lower()
        limits = await self._effective_limits(namespace)
        await self._enforce(
            limits,
            content_type=content_type,
            filename=name,
            size=payload.byte_size,
            ttl_seconds=payload.ttl_seconds,
        )
        expires_at = self._resolve_expiry(payload.ttl_seconds, payload.temporary)
        blob = Blob(
            id=uuid4(),
            namespace=namespace,
            key="",
            filename=name,
            content_type=content_type,
            visibility=payload.visibility,
            status=BlobStatus.PENDING,
            expires_at=expires_at,
            blob_metadata=payload.metadata,
            created_by_namespace=namespace,
        )
        blob.key = self._key(namespace, blob.id, name, temporary=blob.is_temporary)
        blob = await self.repo.create(blob)
        await self.repo.add_event(
            blob.id, namespace, BlobEventAction.CREATED, {"expected_byte_size": payload.byte_size}
        )
        await emit_blob_metric(
            "BlobCreated",
            namespace=namespace,
            Visibility=payload.visibility.value,
            Temporary=str(blob.is_temporary).lower(),
        )
        url = await self.storage.generate_presigned_put(
            blob.key, content_type, settings.s3_presign_expires_seconds
        )
        return blob, url, datetime.now(UTC) + timedelta(seconds=settings.s3_presign_expires_seconds)

    async def complete(self, namespace: str, blob_id: UUID) -> Blob:
        blob = await self.repo.get_for_namespace(blob_id, namespace)
        if blob is None:
            raise NotFoundError()
        try:
            head = await self.storage.head_object(blob.key)
        except NotFoundError as exc:
            await emit_blob_metric("BlobCompleteFailed", namespace=namespace, Reason="not_found")
            raise ConflictError("Uploaded object was not found") from exc

        limits = await self._effective_limits(namespace)
        events = await self.repo.list_events(blob.id)
        expected_size = next(
            (
                event.detail.get("expected_byte_size")
                for event in events
                if event.action == BlobEventAction.CREATED
            ),
            None,
        )
        if expected_size is not None and head.size != expected_size:
            await emit_blob_metric(
                "BlobCompleteFailed", namespace=namespace, Reason="size_mismatch"
            )
            raise ConflictError("Uploaded object size does not match the presign request")
        try:
            await self._enforce(
                limits,
                content_type=blob.content_type,
                filename=blob.filename,
                size=head.size,
                ttl_seconds=None,
            )
        except (PayloadTooLargeError, QuotaExceededError) as exc:
            await emit_blob_metric("BlobCompleteFailed", namespace=namespace, Reason="limit")
            raise ConflictError("Uploaded object violates namespace limits") from exc

        data = await self.storage.get_object(blob.key)
        byte_size = head.size
        original_size: int | None = None
        checksum = hashlib.sha256(data).hexdigest()
        if blob.content_type.startswith("image/") and (
            limits.image_compression_quality is not None or limits.image_max_dimension is not None
        ):
            original_size = len(data)
            original_key = blob.key
            data, content_type = imaging.transform(
                data,
                blob.content_type,
                quality=limits.image_compression_quality,
                max_dimension=limits.image_max_dimension,
            )
            if content_type == "image/webp" and not blob.filename.endswith(".webp"):
                blob.filename = f"{os.path.splitext(blob.filename)[0]}.webp"
                blob.key = self._key(namespace, blob.id, blob.filename, temporary=blob.is_temporary)
            blob.content_type = content_type
            await self.storage.put_object(blob.key, data, content_type)
            if blob.key != original_key:
                await self.storage.delete_object(original_key)
            byte_size = len(data)
            checksum = hashlib.sha256(data).hexdigest()

        blob.status = BlobStatus.STORED
        blob.byte_size = byte_size
        blob.original_byte_size = original_size
        blob.checksum_sha256 = checksum
        blob.updated_by_namespace = namespace
        blob = await self.repo.update(blob)
        await self.repo.add_event(blob.id, namespace, BlobEventAction.COMPLETED)
        await emit_blob_metric("BlobCompleted", namespace=namespace)
        await emit_blob_metric(
            "BlobUploadedBytes",
            byte_size,
            "Bytes",
            namespace=namespace,
            Temporary=str(blob.is_temporary).lower(),
        )
        if original_size is not None:
            await self._emit_compression(namespace, original_size, byte_size)
        return await self._enqueue_processing(blob)
