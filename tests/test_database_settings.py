import pytest
from pydantic import ValidationError

from app.settings.config import Settings


def test_assembles_asyncpg_url_and_quotes_password() -> None:
    settings = Settings(
        _env_file=None,
        database_host="db.example",
        database_port=5432,
        database_user="app user",
        database_password="p@ss:w/rd",
        database_name="blob",
    )
    assert settings.database_url == (
        "postgresql+asyncpg://app%20user:p%40ss%3Aw%2Frd@db.example:5432/blob"
    )


def test_rejects_database_url_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://legacy")
    with pytest.raises(ValidationError, match="DATABASE_URL is no longer read"):
        Settings(_env_file=None, environment="staging")


@pytest.mark.parametrize(
    ("environment", "bucket"),
    [
        ("preprod", "devbutter-staging-blob"),
        ("production", "devbutter-prod-blob"),
    ],
)
def test_selects_aws_bucket_for_deployed_environment(
    environment: str, bucket: str
) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        session_secret="real-secret",
        database_password="real-password",
        service_api_key="key",
        admin_api_key="key",
    )
    assert settings.s3_bucket == bucket
    assert settings.s3_force_path_style is False


def test_rejects_s3_endpoint_outside_development_without_explicit_opt_in() -> None:
    with pytest.raises(ValidationError, match="ALLOW_S3_ENDPOINT_OUTSIDE_DEVELOPMENT"):
        Settings(
            _env_file=None,
            environment="preprod",
            s3_endpoint_url="http://minio:9000",
        )


@pytest.mark.parametrize("environment", ["preprod", "production"])
def test_allows_s3_endpoint_outside_development_with_explicit_opt_in(
    environment: str,
) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        s3_endpoint_url="https://account.r2.cloudflarestorage.com",
        allow_s3_endpoint_outside_development=True,
        session_secret="real-secret",
        database_password="real-password",
        service_api_key="key",
        admin_api_key="key",
    )

    assert settings.s3_endpoint_url == "https://account.r2.cloudflarestorage.com"
