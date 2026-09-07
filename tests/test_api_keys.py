from app.api_keys.repository import ApiKeyRepository
from app.api_keys.service import ApiKeyService
from app.core.exceptions import UnauthorizedError
from app.settings.config import settings


async def test_mint_authenticate_and_revoke(db_session):
    service = ApiKeyService(ApiKeyRepository(db_session))
    key, plain = await service.create("crate-diggr", "worker")

    assert plain.startswith("bbk_")
    assert key.key_hash != plain
    authenticated = await service.authenticate(plain)
    assert authenticated.id == key.id
    assert authenticated.last_used_at is not None

    await service.revoke("crate-diggr", key.id)
    try:
        await service.authenticate(plain)
    except UnauthorizedError:
        pass
    else:  # pragma: no cover - explicit failure keeps the expected exception clear
        raise AssertionError("a revoked key authenticated")


async def test_admin_crud_and_bearer_namespace_identity(client, admin_headers):
    minted = await client.post(
        "/admin/v1/namespaces/crate-diggr/keys",
        headers=admin_headers,
        json={"label": "backend"},
    )
    assert minted.status_code == 201
    created = minted.json()
    assert created["prefix"] == "bbk_"
    assert created["plaintext_key"].startswith("bbk_")

    key_headers = {"Authorization": f"Bearer {created['plaintext_key']}"}
    presign = await client.post(
        "/internal/v1/blobs/presign",
        headers=key_headers,
        json={"filename": "a.txt", "content_type": "text/plain"},
    )
    assert presign.status_code == 201
    blob_id = presign.json()["blob_id"]

    events = await client.get(f"/internal/v1/blobs/{blob_id}/events", headers=key_headers)
    assert events.status_code == 200
    assert events.json()[0]["detail"]["api_key_id"] == created["id"]

    listed = await client.get("/admin/v1/namespaces/crate-diggr/keys", headers=admin_headers)
    assert listed.status_code == 200
    assert "plaintext_key" not in listed.json()[0]

    revoked = await client.post(
        f"/admin/v1/namespaces/crate-diggr/keys/{created['id']}/revoke", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert (await client.get("/admin/v1/namespaces/crate-diggr/keys")).status_code == 404


async def test_bearer_rejects_mismatched_header_and_header_fallback_toggle(client, admin_headers):
    minted = await client.post(
        "/admin/v1/namespaces/crate-diggr/keys", headers=admin_headers, json={"label": "backend"}
    )
    key = minted.json()["plaintext_key"]
    mismatched = await client.get(
        "/internal/v1/namespaces/crate-diggr",
        headers={"Authorization": f"Bearer {key}", "X-Blob-Namespace": "other"},
    )
    assert mismatched.status_code == 403

    settings.allow_header_namespace = False
    legacy = await client.get(
        "/internal/v1/namespaces/crate-diggr",
        headers={"X-Service-Api-Key": "test-service-key", "X-Blob-Namespace": "crate-diggr"},
    )
    assert legacy.status_code == 404
