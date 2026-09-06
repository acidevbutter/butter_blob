# Prompt 03 — Storage layer

**Status:** ✅ done.

## Goal
`BlobStorage` — the only module that imports boto3. Async wrappers over S3
(`asyncio.to_thread`), botocore errors translated to `StorageError` /
`NotFoundError`, plus an in-memory fake for tests.

## Depends on
01 (`StorageError`, `NotFoundError`, `emit_blob_metric`, `settings`).

## Reference
boto3 client construction + `asyncio.to_thread` in
`../butter_relay/app/worker/consumer.py`.

## Files
- `app/core/storage.py`:
  - `HeadObject` — plain result object (`size`, `etag`, `content_type`).
  - `@log_errors class BlobStorage`:
    - `__init__(*, bucket=None)` → `boto3.client("s3", region_name=...,
      endpoint_url=settings.s3_endpoint_url or None, config=Config(
      signature_version="s3v4", s3={"addressing_style": "path" if
      settings.s3_force_path_style else "auto"}))`. Client typed `Any`.
    - `_run(operation, func, *args, **kwargs)` — `await asyncio.to_thread(...)`;
      `ClientError` with a 404-ish code on `head_object` ⇒ `NotFoundError`; any
      other `ClientError` / `BotoCoreError` ⇒ `emit_blob_metric("StorageErrorCount",
      Operation=operation)` + `StorageError`.
    - `put_object(key, data: bytes, content_type)`, `get_object(key) -> bytes`,
      `head_object(key) -> HeadObject`, `delete_object(key)`,
      `generate_presigned_put(key, content_type, expires) -> str`,
      `generate_presigned_get(key, expires, *, disposition=None, filename=None) ->
      str` (sets `ResponseContentDisposition`), `bucket_exists() -> bool`
      (`head_bucket`; returns False, never raises).
  - `get_blob_storage()` singleton + `BlobStorageDep = Annotated[BlobStorage,
    Depends(get_blob_storage)]`.
  - Bind `Any` results to typed locals before returning (avoid `warn_return_any`).
- `tests/fakes.py` — `InMemoryBlobStorage` with the identical interface (dict of
  `key -> (bytes, content_type)`, `bucket_present` flag for the health test,
  deterministic `https://fake-s3.local/...` presigned strings, `head_object` /
  `get_object` on a missing key raise `NotFoundError`).
- `tests/conftest.py` — `blob_storage` fixture installs `InMemoryBlobStorage`.
- `app/main.py` — `/health/ready` already calls `storage.bucket_exists()` (added
  here if it wasn't in 01).

## Acceptance
- `tests/test_storage.py`:
  - `InMemoryBlobStorage` put→head→get→delete round-trip + presigned URL shapes.
  - Real `BlobStorage` under `moto.mock_aws`: create bucket, put/head/get/delete,
    `bucket_exists()` True; missing bucket ⇒ `bucket_exists()` False; `head_object`
    on a missing key ⇒ `NotFoundError`.
  - Monkeypatch `store._client.put_object` to raise `ClientError` and
    `storage_module.emit_blob_metric` to a capture: `put_object` ⇒ `StorageError`
    and exactly one `StorageErrorCount` metric with `{"Operation": "put_object"}`.
- `ruff` / `mypy` clean.

## Notes
`moto[s3]` is a dev dep. moto tests set fake `AWS_*` env vars via a
`monkeypatch.setenv` fixture. `asyncio.to_thread` + moto works (moto patches at
the botocore HTTP layer).
