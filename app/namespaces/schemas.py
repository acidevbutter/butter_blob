from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class NamespaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    description: str | None
    max_storage_bytes: int | None
    max_file_bytes: int | None
    allowed_content_types: list[str] | None
    allowed_extensions: list[str] | None
    image_compression_quality: int | None
    image_max_dimension: int | None
    created_at: datetime
    updated_at: datetime


class NamespaceUsageRead(NamespaceRead):
    blob_count: int
    total_bytes: int
    temporary_count: int


class NamespaceSelfUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class NamespaceLimitsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_storage_bytes: int | None = None
    max_file_bytes: int | None = None
    allowed_content_types: list[str] | None = None
    allowed_extensions: list[str] | None = None
    image_compression_quality: int | None = None
    image_max_dimension: int | None = None

    @field_validator("max_storage_bytes", "max_file_bytes")
    @classmethod
    def non_negative_bytes(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("must be greater than or equal to zero")
        return value

    @field_validator("image_compression_quality")
    @classmethod
    def compression_quality_range(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 100:
            raise ValueError("must be between 1 and 100")
        return value

    @field_validator("allowed_content_types")
    @classmethod
    def normalize_content_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = (
            f".{item.strip().lower().lstrip('.')}" for item in value if item.strip().lstrip(".")
        )
        return list(dict.fromkeys(normalized))


class NamespaceCreate(NamespaceLimitsUpdate):
    slug: str
    name: str = ""
    description: str | None = None
