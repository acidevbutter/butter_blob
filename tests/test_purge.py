from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from app.blobs.models import Blob


async def _temporary_upload(client, headers, name: str) -> dict[str, object]:
    response = await client.post(
        "/internal/v1/blobs",
        headers=headers,
        data={"ttl_seconds": "60"},
        files={"file": (name, b"temporary", "text/plain")},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def test_purge_expired_is_idempotent(client, db_session, internal_headers, blob_storage):
    first = await _temporary_upload(client, internal_headers, "first.txt")
    second = await _temporary_upload(client, internal_headers, "second.txt")
    for item in (first, second):
        blob = await db_session.get(Blob, UUID(str(item["id"])))
        assert blob is not None
        blob.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    purged = await client.post("/internal/v1/maintenance/purge-expired", headers=internal_headers)
    assert purged.status_code == 200
    assert purged.json() == {"scanned": 2, "purged": 2, "bytes_reclaimed": 18}
    assert not blob_storage.objects

    repeated = await client.post("/internal/v1/maintenance/purge-expired", headers=internal_headers)
    assert repeated.json() == {"scanned": 0, "purged": 0, "bytes_reclaimed": 0}
