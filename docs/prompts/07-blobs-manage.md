# Prompt 07 — Blob manage: list / get / download-url / events / patch / delete

**Status:** ⬜ not started.

## Goal
The read/update/delete half of the blobs domain, all owner-scoped.

## Depends on
06.

## Reference
`docs/spec.md` §8.2, §9.2. `../butter_relay/app/messages/router.py` (owner check
pattern: `if blob.namespace != namespace: raise NotFoundError`).

## Files
- `app/blobs/service.py` — add:
  - `list(namespace, filters) -> list[Blob]` → `repo.list(...)`.
  - `get(namespace, blob_id) -> Blob` → `repo.get_for_namespace` else
    `NotFoundError`; if expired ⇒ `GoneError` + `emit_blob_metric("ExpiredBlobRequested")`.
    Add `allow_expired: bool = False` param for internal callers that still need
    metadata (default False).
  - `download_url(namespace, blob_id, *, expires_in, disposition) -> tuple[str,
    datetime]` — `get` (not expired, `status=stored`); clamp `expires_in` to
    `settings.s3_presign_expires_seconds`; `storage.generate_presigned_get(key,
    expires_in, disposition=disposition, filename=blob.filename)`;
    `add_event(DOWNLOADED)`; emit `BlobDownloadUrlIssued` (`Visibility`).
  - `list_events(namespace, blob_id) -> list[BlobEvent]` — `get` then
    `repo.list_events`.
  - `patch(namespace, blob_id, payload: BlobPatch) -> Blob`:
    - `get` (allow expired? no — 410).
    - `filename` → sanitize, update (key stays; it already embeds the id).
    - `metadata` → shallow-merge into `blob_metadata`.
    - `expires_at` in `payload.model_fields_set`: `None` clears (also move key
      prefix `tmp/ → blobs/`? No — leave the key, just clear `expires_at`; document
      that a former-temp blob keeps its `tmp/` key); a value in the future capped
      at `now + max_temporary_ttl_seconds` (over ⇒ `ValidationFailedError`).
    - `visibility`:
      - → `public`: allocate `public_slug` if absent — `secrets.token_urlsafe(12)`
        lowercased to the slug charset; retry (≤3) on `ConflictError`. Emit
        `BlobVisibilityChanged` (`To=public`).
      - → `private`: keep the `public_slug` (so re-publishing is stable) but the
        public routes will 404 on `visibility != public`. Emit
        `BlobVisibilityChanged` (`To=private`).
    - set `updated_by_namespace = namespace`; `add_event(UPDATED)` and, when
      visibility changed, `VISIBILITY_CHANGED` with `detail={"from","to"}`.
    - emit `BlobUpdated`.
  - `delete(namespace, blob_id, *, hard: bool) -> None`:
    - `get` (allow expired — you can still delete an expired blob).
    - `hard`: `storage.delete_object(key)` then `repo.hard_delete(blob)`.
    - soft: `storage.delete_object(key)` (best-effort — log + swallow
      `StorageError`), `repo.soft_delete(blob)` (`status=deleted`, `deleted_at`).
    - `add_event(DELETED, detail={"mode": "hard"|"soft"})`; emit `BlobDeleted`
      (`Mode`), and `BlobDeletedBytes` when the blob was `stored`.
- `app/blobs/router.py` — add:
  - `GET ""` — query params (`visibility`, `status`, `checksum_sha256`,
    `temporary: bool | None`, `expired: bool | None`, `created_after`,
    `created_before`, `limit: int = 100` capped 500) → `list[BlobRead]`.
  - `GET "/{blob_id}"` → `BlobRead`.
  - `GET "/{blob_id}/download-url"` — `expires_in: int | None`, `disposition:
    Literal["inline","attachment"] = "attachment"` → `DownloadUrlResponse`.
  - `GET "/{blob_id}/events"` → `list[BlobEventRead]`.
  - `PATCH "/{blob_id}"` — body `BlobPatch` → `BlobRead`.
  - `DELETE "/{blob_id}"` — `hard: bool = False` → `204` (`status_code=204`,
    return `Response(status_code=204)`).

## Acceptance
`tests/test_blobs_manage.py`:
- every verb 404s for a blob owned by another namespace
- `GET /{id}` on an expired blob ⇒ 410 (`ExpiredBlobRequested` emitted)
- `download-url` returns the fake URL; `expires_in` above the cap is clamped
  (assert the value passed to the fake)
- `PATCH visibility=public` allocates a `public_slug` once; a second PATCH keeps it
- `PATCH metadata` merges (existing keys survive)
- `PATCH expires_at` beyond the cap ⇒ 422; `null` clears it
- soft `DELETE` → `status=deleted`, object gone from the fake, `GET` ⇒ 404; then
  `DELETE ?hard=true` on another blob removes the row
- `events` newest-first and includes `downloaded` after a `download-url` call
- metric assertions for `BlobUpdated`, `BlobVisibilityChanged`, `BlobDeleted(+Bytes)`
- `ruff` / `mypy` / `pytest` green

## Notes
Keep the owner check in exactly one place (`repo.get_for_namespace` +
`NotFoundError` in `service.get`); every route goes through it.
