from tests.fakes import InMemoryBlobStorage


async def test_health_is_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_ok_when_db_and_storage_reachable(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_503_when_bucket_missing(client, blob_storage: InMemoryBlobStorage):
    blob_storage.bucket_present = False
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "object storage unavailable"


async def test_root_redirects_to_docs(client):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
