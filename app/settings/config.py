from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "preprod", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://blob:blob@shared-postgres:5432/blob"

    # Auth -- /internal/v1/* is gated on service_api_key (header X-Service-Api-Key)
    # plus a required X-Blob-Namespace header; /admin/v1/* is gated on admin_api_key.
    service_api_key: str = ""
    admin_api_key: str = ""

    # Object storage. s3_endpoint_url is set only for local dev (MinIO); left unset
    # on AWS so boto3 talks to real S3. s3_force_path_style must be true for MinIO.
    aws_region: str = "us-east-1"
    s3_bucket: str = "devbutter-blob-local"
    s3_endpoint_url: str | None = None
    s3_force_path_style: bool = True
    s3_presign_expires_seconds: int = 900

    # Limits. max_file_bytes / max_storage_bytes / allowed formats / compression
    # are configured per-namespace by an admin; this is the global ceiling.
    max_upload_bytes: int = 52_428_800  # 50 MiB
    default_temporary_ttl_seconds: int = 86_400  # 1 day
    max_temporary_ttl_seconds: int = 604_800  # 7 days

    # Base URL clients use to reach this service's public routes; used to build
    # public_url values echoed in responses.
    public_base_url: str = "http://localhost:8003"


settings = Settings()
