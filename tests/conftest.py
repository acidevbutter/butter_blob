from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.storage import get_blob_storage
from app.db import all_models  # noqa: F401  -- populates Base.metadata
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.settings.config import settings
from tests.fakes import InMemoryBlobStorage

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
TEST_SERVICE_API_KEY = "test-service-key"
TEST_ADMIN_API_KEY = "test-admin-key"
TEST_NAMESPACE = "test-app"


@pytest.fixture(autouse=True)
def _settings_override() -> Iterator[None]:
    original = (
        settings.service_api_key,
        settings.admin_api_key,
        settings.allow_header_namespace,
        settings.public_cdn_base_url,
        settings.cloudfront_distribution_id,
    )
    settings.service_api_key = TEST_SERVICE_API_KEY
    settings.admin_api_key = TEST_ADMIN_API_KEY
    settings.allow_header_namespace = True
    yield
    (
        settings.service_api_key,
        settings.admin_api_key,
        settings.allow_header_namespace,
        settings.public_cdn_base_url,
        settings.cloudfront_distribution_id,
    ) = original


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def blob_storage() -> Iterator[InMemoryBlobStorage]:
    fake = InMemoryBlobStorage()
    app.dependency_overrides[get_blob_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_blob_storage, None)


@pytest.fixture
async def client(
    db_session: AsyncSession, blob_storage: InMemoryBlobStorage
) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def internal_headers() -> dict[str, str]:
    return {
        "X-Service-Api-Key": TEST_SERVICE_API_KEY,
        "X-Blob-Namespace": TEST_NAMESPACE,
    }


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Admin-Api-Key": TEST_ADMIN_API_KEY}
