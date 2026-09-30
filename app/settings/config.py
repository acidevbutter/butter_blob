import os
from typing import Literal
from urllib.parse import quote

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_S3_BUCKET_BY_ENVIRONMENT = {
    # The existing staging bucket is the pre-production bucket.
    "staging": "devbutter-staging-blob",
    "preprod": "devbutter-staging-blob",
    "production": "devbutter-prod-blob",
}


SERVICE_NAME = "butter-blob"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "preprod", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_host: str = "shared-postgres"
    database_port: int = 5432
    database_user: str = "blob"
    database_password: str = "blob"
    database_name: str = "blob"

    # Auth -- bearer keys identify a namespace. The shared header path is retained
    # only during the migration window.
    service_api_key: str = ""
    admin_api_key: str = ""
    allow_header_namespace: bool = True
    session_secret: str = "dev-insecure-change-me"
    session_cookie_name: str = "butter_blob_admin"

    # Object storage. Production-like environments select their AWS bucket from
    # ENVIRONMENT unless S3_BUCKET explicitly overrides it. An external endpoint
    # is opt-in outside development for temporary S3-compatible providers.
    aws_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None
    allow_s3_endpoint_outside_development: bool = False
    # Browser-reachable equivalent of s3_endpoint_url, e.g. http://localhost:9010.
    # boto3 bakes whatever endpoint_url the client was built with into every
    # presigned URL it signs, so in development the internal Docker Compose
    # hostname (s3_endpoint_url=http://minio:9000) would otherwise leak straight
    # into URLs handed to a real browser. When set, BlobStorage rewrites a
    # presigned URL's host from s3_endpoint_url to this value before returning
    # it. Development-only, like s3_endpoint_url itself.
    s3_public_endpoint_url: str | None = None
    s3_force_path_style: bool | None = None
    s3_presign_expires_seconds: int = 900

    # Public permanent blobs can be served by CloudFront while temporary blobs
    # always retain short-lived presigned S3 URLs.
    public_cdn_base_url: str = ""
    cloudfront_distribution_id: str = ""

    # Async post-processing. Celery broker/result backend -- same Redis
    # instance in every environment. Leave redis_url empty to disable workers
    # in an environment; the API then keeps uploads in the stored state.
    redis_url: str = ""
    redis_queue_name: str = "blob-jobs"
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

    @property
    def database_url(self) -> str:
        user = quote(self.database_user, safe="")
        password = quote(self.database_password, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @model_validator(mode="after")
    def reject_legacy_database_url_outside_dev(self) -> "Settings":
        if self.environment != "development" and os.environ.get("DATABASE_URL"):
            raise ValueError(
                "DATABASE_URL is no longer read; set DATABASE_HOST, DATABASE_PORT, "
                "DATABASE_USER, DATABASE_PASSWORD and DATABASE_NAME"
            )
        if (
            self.environment != "development"
            and self.s3_endpoint_url
            and not self.allow_s3_endpoint_outside_development
        ):
            raise ValueError(
                "S3_ENDPOINT_URL outside development requires "
                "ALLOW_S3_ENDPOINT_OUTSIDE_DEVELOPMENT=true"
            )
        if self.environment != "development" and self.s3_public_endpoint_url:
            raise ValueError(
                "S3_PUBLIC_ENDPOINT_URL is only supported in development; real S3 "
                "presigned URLs are already browser-reachable outside development"
            )

        if not self.s3_bucket:
            self.s3_bucket = _S3_BUCKET_BY_ENVIRONMENT.get(self.environment, "devbutter-blob-local")
        if self.s3_force_path_style is None:
            self.s3_force_path_style = self.environment == "development"
        return self

    @model_validator(mode="after")
    def reject_dev_secrets_outside_development(self) -> "Settings":
        if self.environment == "development":
            return self
        defaults = type(self).model_fields
        if self.session_secret == defaults["session_secret"].default:
            raise ValueError(
                "SESSION_SECRET must not be left at its development default outside development"
            )
        if self.database_password == defaults["database_password"].default:
            raise ValueError(
                "DATABASE_PASSWORD must not be left at its development default outside development"
            )
        if not self.service_api_key:
            raise ValueError("SERVICE_API_KEY must be set outside development")
        if not self.admin_api_key:
            raise ValueError("ADMIN_API_KEY must be set outside development")
        return self


settings = Settings()
