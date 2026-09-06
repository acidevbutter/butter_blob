from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.blobs.dependencies import BlobServiceDep
from app.blobs.models import BlobStatus, Visibility
from app.blobs.schemas import (
    BlobEventRead,
    BlobPatch,
    BlobRead,
    DownloadUrlResponse,
    PresignRequest,
    PresignResponse,
)
from app.core.dependencies import CallerNamespace, RequireServiceApiKey
from app.core.exceptions import ValidationFailedError

router = APIRouter(
    prefix="/internal/v1/blobs", tags=["blobs"], dependencies=[RequireServiceApiKey]
)


def _parse_metadata(value: str | None) -> dict[str, Any]:
    if value is None or not value.strip():
        return {}
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("metadata must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValidationFailedError("metadata must be a JSON object")
    return parsed


@router.post("", response_model=BlobRead, status_code=status.HTTP_201_CREATED)
async def upload_blob(
    namespace: CallerNamespace,
    service: BlobServiceDep,
    upload: Annotated[UploadFile, File(alias="file")],
    visibility: Annotated[Visibility, Form()] = Visibility.PRIVATE,
    filename: Annotated[str | None, Form()] = None,
    metadata: Annotated[str | None, Form()] = None,
    ttl_seconds: Annotated[int | None, Form()] = None,
) -> BlobRead:
    blob = await service.upload_proxy(
        namespace,
        upload=upload,
        visibility=visibility,
        filename=filename,
        metadata=_parse_metadata(metadata),
        ttl_seconds=ttl_seconds,
    )
    return service.as_read(blob)


@router.post("/presign", response_model=PresignResponse, status_code=status.HTTP_201_CREATED)
async def create_presign(
    payload: PresignRequest, namespace: CallerNamespace, service: BlobServiceDep
) -> PresignResponse:
    blob, url, expires_at = await service.create_presign(namespace, payload)
    return PresignResponse(
        blob_id=blob.id,
        upload_url=url,
        headers={"Content-Type": blob.content_type},
        expires_at=expires_at,
    )


@router.post("/{blob_id}/complete", response_model=BlobRead)
async def complete_blob(
    blob_id: UUID, namespace: CallerNamespace, service: BlobServiceDep
) -> BlobRead:
    return service.as_read(await service.complete(namespace, blob_id))


@router.get("", response_model=list[BlobRead])
async def list_blobs(
    namespace: CallerNamespace,
    service: BlobServiceDep,
    visibility: Visibility | None = None,
    status_filter: Annotated[BlobStatus | None, Query(alias="status")] = None,
    checksum_sha256: str | None = None,
    temporary: bool | None = None,
    expired: bool | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[BlobRead]:
    blobs = await service.list(
        namespace,
        visibility=visibility,
        status=status_filter,
        checksum=checksum_sha256,
        temporary=temporary,
        expired=expired,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
    )
    return [service.as_read(blob) for blob in blobs]


@router.get("/{blob_id}/download-url", response_model=DownloadUrlResponse)
async def download_url(
    blob_id: UUID,
    namespace: CallerNamespace,
    service: BlobServiceDep,
    expires_in: int | None = None,
    disposition: Literal["inline", "attachment"] = "attachment",
) -> DownloadUrlResponse:
    url, expires_at = await service.download_url(
        namespace, blob_id, expires_in=expires_in, disposition=disposition
    )
    return DownloadUrlResponse(url=url, expires_at=expires_at)


@router.get("/{blob_id}/events", response_model=list[BlobEventRead])
async def list_blob_events(
    blob_id: UUID, namespace: CallerNamespace, service: BlobServiceDep
) -> list[BlobEventRead]:
    return [
        BlobEventRead.model_validate(event)
        for event in await service.list_events(namespace, blob_id)
    ]


@router.get("/{blob_id}", response_model=BlobRead)
async def get_blob(blob_id: UUID, namespace: CallerNamespace, service: BlobServiceDep) -> BlobRead:
    return service.as_read(await service.get(namespace, blob_id))


@router.patch("/{blob_id}", response_model=BlobRead)
async def patch_blob(
    blob_id: UUID, payload: BlobPatch, namespace: CallerNamespace, service: BlobServiceDep
) -> BlobRead:
    return service.as_read(await service.patch(namespace, blob_id, payload))


@router.delete("/{blob_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blob(
    blob_id: UUID,
    namespace: CallerNamespace,
    service: BlobServiceDep,
    hard: bool = False,
) -> Response:
    await service.delete(namespace, blob_id, hard=hard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
