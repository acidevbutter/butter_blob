from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image

from app.blobs.models import Blob, BlobStatus


async def test_proxy_upload_stores_blob_and_bytes(client, internal_headers, blob_storage):
    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("report.txt", b"hello blob", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "stored"
    assert body["checksum_sha256"]
    assert len(blob_storage.objects) == 1
    key, (data, content_type) = next(iter(blob_storage.objects.items()))
    assert key.startswith(f"blobs/{internal_headers['X-Blob-Namespace']}/{body['id']}/")
    assert data == b"hello blob"
    assert content_type == "text/plain"


async def test_presign_then_complete_stores_uploaded_object(
    client, db_session, internal_headers, blob_storage
):
    response = await client.post(
        "/internal/v1/blobs/presign",
        headers=internal_headers,
        json={"filename": "report.txt", "content_type": "text/plain", "byte_size": 5},
    )

    assert response.status_code == 201
    blob_id = response.json()["blob_id"]
    blob = await db_session.get(Blob, UUID(blob_id))
    assert blob is not None and blob.status == BlobStatus.PENDING
    await blob_storage.put_object(blob.key, b"hello", "text/plain")

    completed = await client.post(
        f"/internal/v1/blobs/{blob_id}/complete", headers=internal_headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "stored"
    assert completed.json()["byte_size"] == 5


async def test_upload_rejects_disallowed_format(client, admin_headers, internal_headers):
    created = await client.post(
        "/admin/v1/namespaces",
        headers=admin_headers,
        json={"slug": internal_headers["X-Blob-Namespace"], "allowed_content_types": ["image/png"]},
    )
    assert created.status_code == 201

    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("report.txt", b"blocked", "text/plain")},
    )
    assert response.status_code == 415


@pytest.mark.parametrize(
    ("limits", "upload", "expected_status"),
    [
        ({"max_file_bytes": 1}, b"too large", 413),
        ({"max_storage_bytes": 1}, b"over quota", 507),
    ],
)
async def test_upload_enforces_byte_limits(
    client, admin_headers, internal_headers, limits, upload, expected_status
):
    created = await client.post(
        "/admin/v1/namespaces",
        headers=admin_headers,
        json={"slug": internal_headers["X-Blob-Namespace"], **limits},
    )
    assert created.status_code == 201

    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("report.txt", upload, "text/plain")},
    )
    assert response.status_code == expected_status


async def test_upload_rejects_ttl_over_cap(client, internal_headers):
    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        data={"ttl_seconds": "604801"},
        files={"file": ("report.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422


async def test_complete_rejects_missing_presigned_object(client, internal_headers):
    presign = await client.post(
        "/internal/v1/blobs/presign",
        headers=internal_headers,
        json={"filename": "report.txt", "content_type": "text/plain", "byte_size": 5},
    )
    response = await client.post(
        f"/internal/v1/blobs/{presign.json()['blob_id']}/complete", headers=internal_headers
    )
    assert response.status_code == 409


async def test_upload_compresses_and_resizes_jpeg(client, admin_headers, internal_headers):
    created = await client.post(
        "/admin/v1/namespaces",
        headers=admin_headers,
        json={
            "slug": internal_headers["X-Blob-Namespace"],
            "image_compression_quality": 40,
            "image_max_dimension": 64,
        },
    )
    assert created.status_code == 201
    source = Image.new("RGB", (256, 128), color=(180, 80, 20))
    encoded = BytesIO()
    source.save(encoded, format="JPEG", quality=95)
    source_bytes = encoded.getvalue()

    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("photo.jpg", source_bytes, "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["original_byte_size"] == len(source_bytes)
    assert body["byte_size"] < len(source_bytes)
