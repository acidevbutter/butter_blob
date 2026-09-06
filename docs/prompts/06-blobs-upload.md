# Prompt 06 — Blob upload: proxy + presigned + complete (enforcement + compression)

**Status:** ⬜ not started.

## Goal
The three write entry points, the per-namespace enforcement ladder, and the image
pipeline.

## Depends on
04, 05.

## Reference
`docs/spec.md` §5, §6, §8.2 (Blobs), §9.2. `../butter_relay/app/messages/service.py`
for the `@log_errors` service shape.

## Files
- `app/core/imaging.py` — `transform(data: bytes, content_type: str, *, quality:
  int | None, max_dimension: int | None) -> tuple[bytes, str]`:
  - Non-image (`not content_type.startswith("image/")`) or both params `None` ⇒
    `return data, content_type`.
  - `Image.open(BytesIO(data))`; enforce `Image.MAX_IMAGE_PIXELS` (catch
    `Image.DecompressionBombError` ⇒ raise `UnsupportedMediaTypeError`).
  - If `max_dimension`: `im.thumbnail((max_dimension, max_dimension))`.
  - Re-encode: JPEG → JPEG `quality=quality, optimize=True`; PNG/other raster with
    `quality` set → WebP `quality=quality`; return the new content type.
  - Strip EXIF on re-encode. Return `(out_bytes, out_content_type)`.
  - Pure function, no I/O, no metrics — caller decides what to emit.
- `app/blobs/dependencies.py` — `get_blob_service(db, storage, namespaces) ->
  BlobService`; `BlobServiceDep`. (`storage: BlobStorageDep`,
  `namespaces: NamespaceServiceDep`.)
- `app/blobs/service.py` — `@log_errors class BlobService(repo, storage,
  namespaces)`:
  - `_sanitize_filename(name) -> str` — basename, `[A-Za-z0-9._-]`, ≤200, fallback `file`.
  - `_key(namespace, blob_id, filename, *, temporary) -> str` —
    `f"{'tmp' if temporary else 'blobs'}/{namespace}/{blob_id}/{filename}"`.
  - `_effective_limits(namespace) -> Namespace` — `namespaces.get(namespace)`.
  - `_enforce(ns_limits, *, content_type, filename, size, ttl_seconds)`:
    1. format: `allowed_content_types` / `allowed_extensions` → `UnsupportedMediaTypeError`
       + `emit_blob_metric("UploadRejectedFormat", namespace=...)`
    2. size: `max_file_bytes or settings.max_upload_bytes` → `PayloadTooLargeError`
       + `UploadRejectedTooLarge`
    3. quota: `repo.sum_stored_bytes(ns) + size > max_storage_bytes` →
       `QuotaExceededError` + `UploadRejectedQuota`
    4. ttl: `ttl_seconds and ttl_seconds > settings.max_temporary_ttl_seconds` →
       `ValidationFailedError` + `TtlRejected`
  - `upload_proxy(namespace, *, upload: UploadFile, visibility, filename, metadata,
    ttl_seconds) -> Blob`:
    - read bytes (cap the read at `max_upload_bytes + 1` to reject early), size check
    - `_enforce(...)`
    - `expires_at = now + ttl` if `ttl_seconds` (or default when `temporary` w/o value)
    - if image & (`quality` or `max_dimension`): `imaging.transform` →
      `original_byte_size`, new bytes/content-type, `.webp` filename if changed;
      emit `ImageCompressed` + `CompressionBytesSaved`
    - `checksum_sha256 = hashlib.sha256(bytes).hexdigest()`
    - build key, `storage.put_object`, `repo.create(Blob(status=STORED, ...))`
    - `repo.add_event(blob.id, namespace, CREATED)` + `UPLOADED`
    - emit `BlobCreated` (`Visibility`, `Temporary`), `BlobUploadedBytes`,
      `BlobProxyUploadLatency`
    - return blob (service also sets `public_url` for the schema)
  - `create_presign(namespace, payload: PresignRequest) -> tuple[Blob, str, datetime]`:
    - `_enforce(...)` using `payload.byte_size` (may be `None` → skip size/quota
      precheck but still format + ttl)
    - insert `Blob(status=PENDING, byte_size=None, ...)`, build key,
      `storage.generate_presigned_put(key, content_type, s3_presign_expires_seconds)`
    - `add_event(CREATED)`; emit `BlobCreated`
    - return `(blob, url, expires_at)`
  - `complete(namespace, blob_id) -> Blob`:
    - `repo.get_for_namespace` → 404
    - `head = storage.head_object(key)` — `NotFoundError`/size mismatch vs
      `payload`/`max_file_bytes` ⇒ `ConflictError` + `emit_blob_metric(
      "BlobCompleteFailed", Reason=...)`
    - re-run quota check with `head.size`
    - if image & compression configured: `storage.get_object` →
      `imaging.transform` → `storage.put_object` (replace) → recompute size/checksum
    - set `status=STORED`, `byte_size`, `original_byte_size`, `checksum_sha256`;
      `add_event(COMPLETED)`; emit `BlobCompleted`, `BlobUploadedBytes`
- `app/blobs/router.py` — `APIRouter(prefix="/internal/v1/blobs", tags=["blobs"],
  dependencies=[RequireServiceApiKey])`:
  - `POST ""` — `UploadFile = File(...)`, `Form(...)` fields (`visibility`,
    `filename`, `metadata` JSON string parsed, `ttl_seconds`),
    `namespace: CallerNamespace`, `service: BlobServiceDep` → `201 BlobRead`.
  - `POST "/presign"` — body `PresignRequest` → `201 PresignResponse`.
  - `POST "/{blob_id}/complete"` → `200 BlobRead`.
- `app/main.py` — `include_router(blobs_router)`.

## Acceptance
`tests/test_blobs_upload.py` + `tests/test_imaging.py` (fake storage, monkeypatched
`emit_blob_metric` capture, a tiny real PNG/JPEG built with Pillow):
- proxy happy path → 201, `status=stored`, key `blobs/<ns>/<id>/<file>`, checksum set
- presign → returns fake URL + `pending` row → PUT to fake → `complete` → `stored`
- format reject 415 (+ metric); size reject 413; quota reject 507 (set
  `max_storage_bytes` via admin route first); ttl over cap 422
- namespace with `image_compression_quality=40` → uploaded JPEG comes back with
  `byte_size < original_byte_size`; `CompressionBytesSaved` emitted
- `image_max_dimension=64` → stored image ≤ 64px on the long edge
- `complete` when the object is absent ⇒ 409 (`BlobCompleteFailed`)
- `imaging.transform` unit: passthrough for `text/plain`; JPEG shrink; PNG+quality → WebP
- `ruff` / `mypy` / `pytest` green

## Notes
`python-multipart` is already a dep. Read the upload with a size guard — don't
`await upload.read()` unbounded. `metadata` arrives as a form string → `json.loads`
with a `ValidationFailedError` on bad JSON.
