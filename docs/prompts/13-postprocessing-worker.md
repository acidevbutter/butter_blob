# Prompt 13 — Async post-processing worker

**Status:** ✅ done · **Runner:** Codex · **Phase:** 2.

## Goal
A separate worker process that runs jobs on a blob after it's stored: virus scan,
image thumbnails, (stub) video transcode — without blocking the upload response.

## Depends on
06, 07, 08.

## Reference
`../butter_relay/app/worker/*` — `python -m app.worker`, `asyncio.to_thread`
around blocking SDK calls, `@log_call` on the top handler, "don't ack on failure"
retry semantics, `session_factory` reuse. `../butter_relay/docker-compose.yml`
(`worker` service + `elasticmq` dev profile).

## Files
- `app/settings/config.py` — `blob_jobs_queue_url: str = ""`,
  `blob_jobs_endpoint_url: str | None = None`, `clamav_host: str | None = None`,
  `clamav_port: int = 3310`, `thumbnail_widths: list[int] = [256]`,
  `enable_video_transcode: bool = False`. `.env.example` updated.
- `app/blobs/models.py` — add `PROCESSING = "processing"` to `BlobStatus`; add
  `PROCESSING` / `PROCESSED` / `QUARANTINED` to `BlobEventAction`. Migration.
- `app/blobs/service.py` — after a successful `upload_proxy` / `complete`, if any
  job applies (namespace config or global), set `status=PROCESSING` and enqueue
  `{blob_id, namespace, kinds:[...]}` via a new `app/core/jobs.py`
  (`enqueue(job: dict)` → boto3 SQS `send_message`, `asyncio.to_thread`). If no
  job applies, stay `STORED`.
- `app/core/jobs.py` — SQS client build + `enqueue`.
- `app/worker/__init__.py`, `app/worker/__main__.py` (`setup_logging` +
  `asyncio.run(run_forever())`), `app/worker/consumer.py`:
  - `run_forever()` — long-poll `receive_message`; per message `process_job`;
    delete on success, leave on failure (SQS visibility-timeout retry → DLQ).
  - `@log_call async def process_job(msg)` — open `session_factory()`, build repo +
    storage, dispatch by `kind`:
    - `virus_scan` — stream bytes to `clamd` (`INSTREAM`) via a socket in a thread;
      on hit: `repo.soft_delete`, `storage.delete_object`, `add_event(QUARANTINED,
      detail={"signature": name})`, `emit_blob_metric("BlobQuarantined",
      namespace=...)`. Clean ⇒ continue.
    - `image_thumbnail` — `get_object` → Pillow → for each width, `put_object`
      sidecar key `…/thumb_<w>.webp`; record under `blob_metadata["derived"]`
      (list of `{width, key}`); `emit_blob_metric("ThumbnailCreated", ...)`.
    - `video_transcode` — behind `enable_video_transcode`: shell out to `ffmpeg`
      (documented interface only; may raise `NotImplementedError` until wired).
  - On all jobs done: `status=STORED` (or keep `DELETED` if quarantined),
    `add_event(PROCESSED)`.
- `docker-compose.yml` — add `worker` service (`command: python -m app.worker`,
  same image, no port) and an `elasticmq` dev-profile service (mirror relay).
  `.env` gets `BLOB_JOBS_ENDPOINT_URL=http://elasticmq:9324`.
- `Dockerfile` — unchanged (one image; compose overrides `command`).
- `app/db/all_models.py` — no new model, but the enum/column change needs a migration.

## Acceptance
`tests/test_worker.py` (moto SQS or a fake queue, `AsyncMock` for clamd/ffmpeg):
- upload of a type with thumbnails configured → row goes `PROCESSING`, a job is
  enqueued; running `process_job` creates the sidecar keys and returns to `STORED`
  with `blob_metadata["derived"]` populated
- a "virus-positive" clamd stub → blob soft-deleted, `QUARANTINED` event,
  `BlobQuarantined` metric, message acked
- `process_job` raising → message NOT deleted (retryable)
- when no job applies, upload stays `STORED` and nothing is enqueued
- `ruff` / `mypy` / `pytest` green

## Notes
Keep the API's response-time contract: the upload endpoint returns as soon as the
row + object exist; processing is entirely out-of-band. Consumers that need the
final state poll `GET /internal/v1/blobs/{id}` for `status`.
