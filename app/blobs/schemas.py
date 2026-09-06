import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.blobs.models import BlobEventAction, BlobStatus, Visibility


class BlobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    namespace: str
    filename: str
    content_type: str
    byte_size: int | None
    original_byte_size: int | None
    checksum_sha256: str | None
    visibility: Visibility
    status: BlobStatus
    public_slug: str | None
    public_url: str | None = None
    is_temporary: bool
    expires_at: datetime | None
    metadata: dict[str, Any] = Field(alias="blob_metadata")
    created_at: datetime
    updated_at: datetime


class BlobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: BlobEventAction
    detail: dict[str, Any]
    at: datetime


class PresignRequest(BaseModel):
    filename: str
    content_type: str
    byte_size: int | None = None
    visibility: Visibility = Visibility.PRIVATE
    metadata: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int | None = None


class PresignResponse(BaseModel):
    blob_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_at: datetime


class BlobPatch(BaseModel):
    visibility: Visibility | None = None
    filename: str | None = None
    metadata: dict[str, Any] | None = None
    expires_at: datetime | None = None


class DownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime


class PurgeResult(BaseModel):
    scanned: int
    purged: int
    bytes_reclaimed: int


class PublicMeta(BaseModel):
    filename: str
    content_type: str
    byte_size: int | None
    created_at: datetime
    expires_at: datetime | None
