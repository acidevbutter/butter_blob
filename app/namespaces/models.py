import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Namespace(Base):
    __tablename__ = "namespaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    max_storage_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    max_file_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    allowed_content_types: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    allowed_extensions: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    image_compression_quality: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    image_max_dimension: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
