import pytest
from pydantic import ValidationError

from app.settings.config import Settings


def test_development_allows_default_secrets() -> None:
    settings = Settings(_env_file=None, environment="development")
    assert settings.session_secret == "dev-insecure-change-me"


@pytest.mark.parametrize("environment", ["staging", "preprod", "production"])
def test_non_dev_rejects_default_session_secret(environment: str) -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings(
            _env_file=None,
            environment=environment,
            database_password="real-password",
            service_api_key="key",
            admin_api_key="key",
        )


def test_non_dev_rejects_default_database_password() -> None:
    with pytest.raises(ValidationError, match="DATABASE_PASSWORD"):
        Settings(
            _env_file=None,
            environment="staging",
            session_secret="real-secret",
            service_api_key="key",
            admin_api_key="key",
        )


def test_non_dev_rejects_empty_service_api_key() -> None:
    with pytest.raises(ValidationError, match="SERVICE_API_KEY"):
        Settings(
            _env_file=None,
            environment="staging",
            session_secret="real-secret",
            database_password="real-password",
            service_api_key="",
            admin_api_key="key",
        )


def test_non_dev_rejects_empty_admin_api_key() -> None:
    with pytest.raises(ValidationError, match="ADMIN_API_KEY"):
        Settings(
            _env_file=None,
            environment="staging",
            session_secret="real-secret",
            database_password="real-password",
            service_api_key="key",
            admin_api_key="",
        )


def test_non_dev_valid_config_passes() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        session_secret="real-secret",
        database_password="real-password",
        service_api_key="key",
        admin_api_key="key",
    )
    assert settings.session_secret == "real-secret"
