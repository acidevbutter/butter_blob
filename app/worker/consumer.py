"""SQS consumer. Failed jobs are deliberately not acknowledged for retry/DLQ."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import socket
import struct
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from PIL import Image

from app.blobs.models import BlobEventAction, BlobStatus
from app.blobs.repository import BlobRepository
from app.core.decorators import log_call
from app.core.jobs import build_sqs_client
from app.core.observability import emit_blob_metric
from app.core.storage import BlobStorage
from app.db.session import session_factory
from app.settings.config import settings

logger = logging.getLogger(__name__)


def _clamd_scan(host: str, port: int, data: bytes) -> str | None:
    """Return a ClamAV signature when infected, otherwise None."""
    with socket.create_connection((host, port), timeout=30) as connection:
        connection.sendall(b"zINSTREAM\0")
        for start in range(0, len(data), 65_536):
            chunk = data[start : start + 65_536]
            connection.sendall(struct.pack("!I", len(chunk)))
            connection.sendall(chunk)
        connection.sendall(struct.pack("!I", 0))
        response = connection.recv(4096).decode("utf-8", errors="replace").strip()
    if response.endswith("OK"):
        return None
    if " FOUND" in response:
        return response.rsplit(" FOUND", 1)[0].rsplit(":", 1)[-1].strip()
    raise RuntimeError(f"Unexpected clamd response: {response}")


async def _scan_for_virus(data: bytes) -> str | None:
    if not settings.clamav_host:
        return None
    return await asyncio.to_thread(_clamd_scan, settings.clamav_host, settings.clamav_port, data)


async def _create_thumbnails(
    storage: BlobStorage, key: str, data: bytes
) -> list[dict[str, object]]:
    derived: list[dict[str, object]] = []
    directory = key.rsplit("/", 1)[0]
    for width in settings.thumbnail_widths:
        if width <= 0:
            continue
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("RGBA")
            image.thumbnail((width, width))
            output = io.BytesIO()
            image.save(output, format="WEBP")
        thumb_key = f"{directory}/thumb_{width}.webp"
        await storage.put_object(thumb_key, output.getvalue(), "image/webp")
        derived.append({"width": width, "key": thumb_key})
    return derived


async def _transcode_video() -> None:
    # The worker contract reserves this kind. Actual ffmpeg wiring needs a
    # bounded scratch volume and output profile before it can be enabled.
    raise NotImplementedError("Video transcoding is not wired yet")


def _job_payload(message: Mapping[str, Any]) -> dict[str, Any]:
    body = message.get("Body", message)
    if isinstance(body, str):
        parsed = json.loads(body)
    elif isinstance(body, Mapping):
        parsed = dict(body)
    else:
        raise ValueError("SQS message body must be a JSON object")
    if not isinstance(parsed.get("blob_id"), str) or not isinstance(parsed.get("namespace"), str):
        raise ValueError("Blob job requires blob_id and namespace")
    kinds = parsed.get("kinds")
    if not isinstance(kinds, list) or not all(isinstance(kind, str) for kind in kinds):
        raise ValueError("Blob job requires a list of kinds")
    return dict(parsed)


@log_call
async def process_job(
    message: Mapping[str, Any],
    *,
    storage: BlobStorage | None = None,
    session_factory_override: Any | None = None,
) -> None:
    """Process one job. Raising keeps the SQS message visible for retry."""
    payload = _job_payload(message)
    blob_id = UUID(payload["blob_id"])
    namespace = payload["namespace"]
    kinds = payload["kinds"]

    factory = session_factory_override or session_factory
    async with factory() as session:
        repo = BlobRepository(session)
        storage = storage or BlobStorage()
        blob = await repo.get_for_namespace(blob_id, namespace)
        if blob is None or blob.status == BlobStatus.DELETED:
            return

        for kind in kinds:
            if kind == "virus_scan":
                signature = await _scan_for_virus(await storage.get_object(blob.key))
                if signature is not None:
                    await repo.soft_delete(blob)
                    await storage.delete_object(blob.key)
                    await repo.add_event(
                        blob.id,
                        namespace,
                        BlobEventAction.QUARANTINED,
                        {"signature": signature},
                    )
                    await emit_blob_metric("BlobQuarantined", namespace=namespace)
                    break
            elif kind == "image_thumbnail":
                data = await storage.get_object(blob.key)
                derived = await _create_thumbnails(storage, blob.key, data)
                metadata = dict(blob.blob_metadata or {})
                existing = metadata.get("derived", [])
                existing_derived = existing if isinstance(existing, list) else []
                widths = {item["width"] for item in derived}
                metadata["derived"] = [
                    item
                    for item in existing_derived
                    if not isinstance(item, dict) or item.get("width") not in widths
                ] + derived
                blob.blob_metadata = metadata
                blob = await repo.update(blob)
                await emit_blob_metric(
                    "ThumbnailCreated", float(len(derived)), "Count", namespace=namespace
                )
            elif kind == "video_transcode":
                if settings.enable_video_transcode:
                    await _transcode_video()
            else:
                raise ValueError(f"Unknown blob job kind: {kind}")

        if blob.status != BlobStatus.DELETED:
            blob.status = BlobStatus.STORED
            await repo.update(blob)
        await repo.add_event(blob.id, namespace, BlobEventAction.PROCESSED)


async def run_forever() -> None:
    """Long-poll SQS and ack only successful jobs."""
    if not settings.blob_jobs_queue_url:
        logger.warning("BLOB_JOBS_QUEUE_URL is empty; worker is disabled")
        return
    client = build_sqs_client()
    while True:
        response = await asyncio.to_thread(
            client.receive_message,
            QueueUrl=settings.blob_jobs_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            VisibilityTimeout=60,
        )
        messages = response.get("Messages", [])
        if isinstance(messages, list):
            await process_messages(client, messages)


async def process_messages(client: Any, messages: list[Mapping[str, Any]]) -> None:
    """Acknowledge only messages whose post-processing completed successfully."""
    for message in messages:
        try:
            await process_job(message)
        except Exception:
            logger.exception("Blob job failed; leaving message for retry")
            continue
        receipt_handle = message.get("ReceiptHandle")
        if isinstance(receipt_handle, str):
            await asyncio.to_thread(
                client.delete_message,
                QueueUrl=settings.blob_jobs_queue_url,
                ReceiptHandle=receipt_handle,
            )
