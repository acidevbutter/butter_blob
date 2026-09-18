from io import BytesIO
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from PIL import Image

from app.blobs.models import Blob, BlobEventAction, BlobStatus, Visibility
from app.blobs.repository import BlobRepository
from app.worker import tasks


def _png() -> bytes:
    image = Image.new("RGB", (512, 256), color=(40, 90, 120))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def test_image_job_creates_thumbnail_and_marks_blob_stored(
    client, db_session, internal_headers, blob_storage, monkeypatch
):
    queued = AsyncMock()
    monkeypatch.setattr("app.blobs.service.enqueue", queued)
    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("photo.png", _png(), "image/png")},
    )

    assert response.status_code == 201
    blob_id = UUID(response.json()["id"])
    assert response.json()["status"] == BlobStatus.PROCESSING.value
    queued.assert_awaited_once()
    call = queued.await_args
    assert call is not None
    job = call.args[0]
    assert job["kinds"] == ["image_thumbnail"]

    await tasks.process_job(
        job["blob_id"],
        job["namespace"],
        job["kinds"],
        storage=blob_storage,
        session_factory_override=lambda: db_session,
    )

    blob = await db_session.get(Blob, blob_id)
    assert blob is not None and blob.status == BlobStatus.STORED
    derived = blob.blob_metadata["derived"]
    assert derived == [{"width": 256, "key": f"blobs/test-app/{blob_id}/thumb_256.webp"}]
    assert derived[0]["key"] in blob_storage.objects


async def test_virus_hit_quarantines_blob(db_session, blob_storage, monkeypatch):
    blob = Blob(
        id=uuid4(),
        namespace="test-app",
        key="blobs/test-app/infected/file.txt",
        filename="file.txt",
        content_type="text/plain",
        byte_size=7,
        visibility=Visibility.PRIVATE,
        status=BlobStatus.PROCESSING,
        blob_metadata={},
        created_by_namespace="test-app",
    )
    db_session.add(blob)
    await db_session.commit()
    await blob_storage.put_object(blob.key, b"infected", "text/plain")
    monkeypatch.setattr(tasks, "_scan_for_virus", AsyncMock(return_value="Test.Signature"))
    quarantined = AsyncMock()
    monkeypatch.setattr(tasks, "emit_blob_metric", quarantined)

    await tasks.process_job(
        str(blob.id),
        "test-app",
        ["virus_scan"],
        storage=blob_storage,
        session_factory_override=lambda: db_session,
    )

    stored = await db_session.get(Blob, blob.id)
    assert stored is not None and stored.status == BlobStatus.DELETED
    assert blob.key not in blob_storage.objects
    events = await BlobRepository(db_session).list_events(blob.id)
    assert BlobEventAction.QUARANTINED in [event.action for event in events]
    quarantined.assert_awaited_once_with("BlobQuarantined", namespace="test-app")


async def test_upload_without_applicable_jobs_stays_stored(
    client, internal_headers, monkeypatch
):
    queued = AsyncMock()
    monkeypatch.setattr("app.blobs.service.enqueue", queued)
    monkeypatch.setattr("app.blobs.service.settings.thumbnail_widths", [])
    response = await client.post(
        "/internal/v1/blobs",
        headers=internal_headers,
        files={"file": ("photo.png", _png(), "image/png")},
    )

    assert response.status_code == 201
    assert response.json()["status"] == BlobStatus.STORED.value
    queued.assert_not_awaited()


def test_process_job_task_runs_process_job_and_lets_failures_propagate(monkeypatch):
    """process_job_task is a thin sync/async bridge -- autoretry_for=(Exception,)
    on the Celery task decorator is what actually turns a raised exception into
    a bounded, backed-off retry; here we only prove the bridge itself calls
    process_job and re-raises unchanged, since that's the part our code owns.

    Plain `def`, not `async def`: process_job_task drives its own persistent
    event loop (one per forked worker process, reused across tasks -- see
    `_get_worker_loop`) via `run_until_complete`, so this must not run inside
    the loop pytest-asyncio would otherwise wrap an `async def` test in.
    """
    failing = AsyncMock(side_effect=RuntimeError("retry me"))
    monkeypatch.setattr(tasks, "process_job", failing)

    try:
        tasks.process_job_task.run(blob_id="b", namespace="n", kinds=["virus_scan"])
    except RuntimeError as exc:
        assert str(exc) == "retry me"
    else:
        raise AssertionError("expected RuntimeError to propagate")

    failing.assert_awaited_once_with("b", "n", ["virus_scan"])
