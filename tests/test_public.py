from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from app.blobs.models import Blob
from app.settings.config import settings


async def _upload(client, headers, *, visibility: str = "private") -> dict[str, object]:
    response = await client.post(
        "/internal/v1/blobs",
        headers=headers,
        files={"file": ("public.txt", b"public blob", "text/plain")},
        data={"visibility": visibility},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def _publish(client, headers) -> dict[str, object]:
    blob = await _upload(client, headers)
    response = await client.patch(
        f"/internal/v1/blobs/{blob['id']}", headers=headers, json={"visibility": "public"}
    )
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


async def test_public_blob_redirects_without_auth(client, internal_headers):
    blob = await _publish(client, internal_headers)
    response = await client.get(
        f"/v1/public/{internal_headers['X-Blob-Namespace']}/{blob['public_slug']}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://fake-s3.local/")
    assert "method=GET" in response.headers["location"]
    assert "expires=300" in response.headers["location"]
    assert response.headers["cache-control"] == "public, max-age=86400"


async def test_private_and_unknown_public_blobs_are_not_found(client, internal_headers):
    private_blob = await _upload(client, internal_headers)
    namespace = internal_headers["X-Blob-Namespace"]
    for slug in (str(private_blob["id"]), "unknown"):
        response = await client.get(f"/v1/public/{namespace}/{slug}", follow_redirects=False)
        assert response.status_code == 404


async def test_expired_public_blob_is_gone(client, db_session, internal_headers):
    blob = await _publish(client, internal_headers)
    stored = await db_session.get(Blob, UUID(str(blob["id"])))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    namespace = internal_headers["X-Blob-Namespace"]
    response = await client.get(
        f"/v1/public/{namespace}/{blob['public_slug']}", follow_redirects=False
    )

    assert response.status_code == 410


async def test_public_metadata_has_only_public_fields(client, internal_headers):
    blob = await _publish(client, internal_headers)
    response = await client.get(
        f"/v1/public/{internal_headers['X-Blob-Namespace']}/{blob['public_slug']}/meta"
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "filename",
        "content_type",
        "byte_size",
        "created_at",
        "expires_at",
    }
    assert response.headers["cache-control"] == "public, max-age=86400"


async def test_permanent_public_blob_uses_cdn_and_temporary_blob_does_not(
    client, internal_headers
):
    settings.public_cdn_base_url = "https://cdn.example.test"
    permanent = await _publish(client, internal_headers)
    permanent_response = await client.get(
        f"/v1/public/{internal_headers['X-Blob-Namespace']}/{permanent['public_slug']}",
        follow_redirects=False,
    )
    assert permanent_response.headers["location"].startswith("https://cdn.example.test/blobs/")
    assert permanent_response.headers["cache-control"] == "public, max-age=86400"

    temporary_response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("temporary.txt", b"temporary", "text/plain")},
        data={"visibility": "public", "ttl_seconds": "60"},
    )
    assert temporary_response.status_code == 201
    temporary = cast(dict[str, object], temporary_response.json())
    response = await client.get(
        f"/v1/public/{internal_headers['X-Blob-Namespace']}/{temporary['public_slug']}",
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("https://fake-s3.local/")
    assert response.headers["cache-control"] == "no-store"
