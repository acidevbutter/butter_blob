import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Visibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class BlobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    STORED = "stored"
    DELETED = "deleted"


class BlobEventAction(str, enum.Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    COMPLETED = "completed"
    UPDATED = "updated"
    VISIBILITY_CHANGED = "visibility_changed"
    DOWNLOADED = "downloaded"
    DELETED = "deleted"
    EXPIRED = "expired"
    PROCESSING = "processing"
    PROCESSED = "processed"
    QUARANTINED = "quarantined"


class Blob(Base):
    __tablename__ = "blobs"
    __table_args__ = (UniqueConstraint("namespace", "key", name="uq_blob_namespace_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    namespace: Mapped[str] = mapped_column(String(100), index=True)
    key: Mapped[str] = mapped_column(String(1024))
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(255))
    byte_size: Mapped[int | None] = mapped_column(BigInteger, default=None)
    original_byte_size: Mapped[int | None] = mapped_column(BigInteger, default=None)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    visibility: Mapped[Visibility] = mapped_column(String(20), default=Visibility.PRIVATE)
    status: Mapped[BlobStatus] = mapped_column(String(20), default=BlobStatus.PENDING, index=True)
    public_slug: Mapped[str | None] = mapped_column(String(160), default=None, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    blob_metadata: Mapped[dict[str, Any]] = mapped_column("blob_metadata", JSON, default=dict)
    created_by_namespace: Mapped[str] = mapped_column(String(100))
    updated_by_namespace: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @property
    def is_temporary(self) -> bool:
        return self.expires_at is not None


class BlobEvent(Base):
    __tablename__ = "blob_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    blob_id: Mapped[uuid.UUID] = mapped_column(index=True)
    namespace: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[BlobEventAction] = mapped_column(String(30))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        index=True,
    )
