from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from app.blobs.models import Blob


async def _upload(client, headers) -> dict[str, object]:
    response = await client.post(
        "/internal/v1/blobs",
        headers=headers,
        files={"file": ("report.txt", b"hello blob", "text/plain")},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def test_blob_management_is_owner_scoped_and_preserves_public_slug(client, internal_headers):
    blob = await _upload(client, internal_headers)
    blob_id = blob["id"]
    other_headers = {**internal_headers, "X-Blob-Namespace": "other-app"}

    other_response = await client.get(f"/internal/v1/blobs/{blob_id}", headers=other_headers)
    assert other_response.status_code == 404

    published = await client.patch(
        f"/internal/v1/blobs/{blob_id}",
        headers=internal_headers,
        json={"visibility": "public", "metadata": {"source": "test"}},
    )
    assert published.status_code == 200
    public_slug = published.json()["public_slug"]
    assert public_slug

    updated = await client.patch(
        f"/internal/v1/blobs/{blob_id}",
        headers=internal_headers,
        json={"metadata": {"version": 2}},
    )
    assert updated.status_code == 200
    assert updated.json()["public_slug"] == public_slug
    assert updated.json()["blob_metadata"] == {"source": "test", "version": 2}

    download = await client.get(
        f"/internal/v1/blobs/{blob_id}/download-url?expires_in=999999",
        headers=internal_headers,
    )
    assert download.status_code == 200
    assert "method=GET" in download.json()["url"]
    events = await client.get(f"/internal/v1/blobs/{blob_id}/events", headers=internal_headers)
    assert events.status_code == 200
    assert events.json()[0]["action"] == "downloaded"


async def test_expired_blob_returns_gone_and_soft_delete_hides_blob(
    client, db_session, internal_headers, blob_storage
):
    blob = await _upload(client, internal_headers)
    blob_id = blob["id"]
    stored = await db_session.get(Blob, UUID(str(blob_id)))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client.get(f"/internal/v1/blobs/{blob_id}", headers=internal_headers)
    assert expired.status_code == 410

    deleted = await client.delete(f"/internal/v1/blobs/{blob_id}", headers=internal_headers)
    assert deleted.status_code == 204
    assert not blob_storage.objects
    missing = await client.get(f"/internal/v1/blobs/{blob_id}", headers=internal_headers)
    assert missing.status_code == 404


async def test_public_delete_and_visibility_private_invalidate_cdn(
    client, internal_headers, monkeypatch
):
    invalidated: list[list[str]] = []

    async def fake_invalidate(paths: list[str]) -> None:
        invalidated.append(paths)

    monkeypatch.setattr("app.blobs.service.invalidate", fake_invalidate)
    blob = await _upload(client, internal_headers)
    blob_id = str(blob["id"])
    published = await client.patch(
        f"/internal/v1/blobs/{blob_id}", headers=internal_headers, json={"visibility": "public"}
    )
    assert published.status_code == 200
    private = await client.patch(
        f"/internal/v1/blobs/{blob_id}", headers=internal_headers, json={"visibility": "private"}
    )
    assert private.status_code == 200
    deleted = await client.delete(f"/internal/v1/blobs/{blob_id}", headers=internal_headers)
    assert deleted.status_code == 204
    key = f"blobs/{internal_headers['X-Blob-Namespace']}/{blob_id}/report.txt"
    assert invalidated == [[key], [key]]
