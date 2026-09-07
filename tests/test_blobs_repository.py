from datetime import UTC, datetime, timedelta

import pytest

from app.blobs.models import Blob, BlobEventAction, BlobStatus, Visibility
from app.blobs.repository import BlobRepository
from app.core.exceptions import ConflictError


def make_blob(
    namespace: str = "test-app",
    key: str = "blobs/test-app/one/file.txt",
    **overrides: object,
) -> Blob:
    values: dict[str, object] = {
        "namespace": namespace,
        "key": key,
        "filename": "file.txt",
        "content_type": "text/plain",
        "created_by_namespace": namespace,
    }
    values.update(overrides)
    return Blob(**values)


async def test_create_get_and_namespace_ownership(db_session) -> None:
    repo = BlobRepository(db_session)
    blob = await repo.create(make_blob())

    assert await repo.get(blob.id) == blob
    assert await repo.get_for_namespace(blob.id, "test-app") == blob
    assert await repo.get_for_namespace(blob.id, "other-app") is None


async def test_list_filters_ordering_and_limit(db_session) -> None:
    repo = BlobRepository(db_session)
    now = datetime.now(UTC)
    old = await repo.create(
        make_blob(
            key="old",
            status=BlobStatus.STORED,
            visibility=Visibility.PUBLIC,
            checksum_sha256="same",
            expires_at=now - timedelta(hours=1),
            created_at=now - timedelta(minutes=2),
        )
    )
    new = await repo.create(
        make_blob(
            key="new",
            status=BlobStatus.STORED,
            visibility=Visibility.PUBLIC,
            checksum_sha256="same",
            expires_at=now + timedelta(hours=1),
            created_at=now - timedelta(minutes=1),
        )
    )
    permanent = await repo.create(
        make_blob(key="permanent", status=BlobStatus.PENDING, created_at=now)
    )

    assert await repo.list("test-app", status=BlobStatus.PENDING) == [permanent]
    assert await repo.list("test-app", visibility=Visibility.PUBLIC) == [new, old]
    assert await repo.list("test-app", checksum="same") == [new, old]
    assert await repo.list("test-app", temporary=True) == [new, old]
    assert await repo.list("test-app", temporary=False) == [permanent]
    assert await repo.list("test-app", expired=True) == [old]
    assert await repo.list("test-app", expired=False) == [permanent, new]
    assert await repo.list("test-app", limit=1) == [permanent]


async def test_sum_stored_bytes_and_iter_expired(db_session) -> None:
    repo = BlobRepository(db_session)
    now = datetime.now(UTC)
    stored = await repo.create(
        make_blob(
            key="stored",
            status=BlobStatus.STORED,
            byte_size=7,
            expires_at=now - timedelta(days=1),
        )
    )
    await repo.create(make_blob(key="pending", status=BlobStatus.PENDING, byte_size=9))
    await repo.create(make_blob(key="deleted", status=BlobStatus.DELETED, byte_size=11))
    await repo.create(
        make_blob(
            key="not-expired",
            status=BlobStatus.STORED,
            expires_at=now + timedelta(days=1),
        )
    )

    assert await repo.sum_stored_bytes("test-app") == 7
    assert await repo.iter_expired(now) == [stored]


async def test_duplicate_namespace_key_and_public_slug_are_conflicts(db_session) -> None:
    repo = BlobRepository(db_session)
    await repo.create(make_blob(key="duplicate"))
    with pytest.raises(ConflictError):
        await repo.create(make_blob(key="duplicate"))

    await repo.create(make_blob(key="first-slug", public_slug="shared"))
    with pytest.raises(ConflictError):
        await repo.create(make_blob(key="second-slug", public_slug="shared"))


async def test_events_are_newest_first(db_session) -> None:
    repo = BlobRepository(db_session)
    blob = await repo.create(make_blob())
    created = await repo.add_event(blob.id, blob.namespace, BlobEventAction.CREATED)
    uploaded = await repo.add_event(blob.id, blob.namespace, BlobEventAction.UPLOADED)
    uploaded.at = created.at + timedelta(seconds=1)
    await db_session.commit()

    assert await repo.list_events(blob.id) == [uploaded, created]
