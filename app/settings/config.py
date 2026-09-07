from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "preprod", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://blob:blob@shared-postgres:5432/blob"

    # Auth -- bearer keys identify a namespace. The shared header path is retained
    # only during the migration window.
    service_api_key: str = ""
    admin_api_key: str = ""
    allow_header_namespace: bool = True
    session_secret: str = "dev-insecure-change-me"
    session_cookie_name: str = "butter_blob_admin"

    # Object storage. s3_endpoint_url is set only for local dev (MinIO); left unset
    # on AWS so boto3 talks to real S3. s3_force_path_style must be true for MinIO.
    aws_region: str = "us-east-1"
    s3_bucket: str = "devbutter-blob-local"
    s3_endpoint_url: str | None = None
    s3_force_path_style: bool = True
    s3_presign_expires_seconds: int = 900

    # Public permanent blobs can be served by CloudFront while temporary blobs
    # always retain short-lived presigned S3 URLs.
    public_cdn_base_url: str = ""
    cloudfront_distribution_id: str = ""

    # Async post-processing. Leave blob_jobs_queue_url empty to disable workers
    # in an environment; the API then keeps uploads in the stored state.
    blob_jobs_queue_url: str = ""
    blob_jobs_endpoint_url: str | None = None
    clamav_host: str | None = None
    clamav_port: int = 3310
    thumbnail_widths: list[int] = [256]
    enable_video_transcode: bool = False

    # Limits. max_file_bytes / max_storage_bytes / allowed formats / compression
    # are configured per-namespace by an admin; this is the global ceiling.
    max_upload_bytes: int = 52_428_800  # 50 MiB
    default_temporary_ttl_seconds: int = 86_400  # 1 day
    max_temporary_ttl_seconds: int = 604_800  # 7 days

    # Base URL clients use to reach this service's public routes; used to build
    # public_url values echoed in responses.
    public_base_url: str = "http://localhost:8003"

    @field_validator("thumbnail_widths", mode="before")
    @classmethod
    def normalize_thumbnail_widths(cls, value: object) -> object:
        """Accept the documented single-width env form (``THUMBNAIL_WIDTHS=256``)."""
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(width.strip()) for width in value.split(",") if width.strip()]
        return value


settings = Settings()
