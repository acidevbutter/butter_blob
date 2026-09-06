# Prompt 08 — Temporary files & purge-expired

**Status:** ⬜ not started.

## Goal
Make `ttl_seconds` a first-class, end-to-end feature and add the reclamation
endpoint.

## Depends on
06, 07.

## Reference
`docs/spec.md` §2 (temporary blob), §8.2 (Maintenance), §9.2.

## Files
- `app/blobs/schemas.py` — confirm `ttl_seconds` on `PresignRequest` and as a
  proxy-upload form field; add `temporary: bool = False` to the proxy form
  (when `true` with no `ttl_seconds`, use `settings.default_temporary_ttl_seconds`).
- `app/blobs/service.py` — factor the ttl → `expires_at` decision into
  `_resolve_expiry(ttl_seconds: int | None, temporary: bool) -> datetime | None`:
  - `ttl_seconds` given → cap-check → `now + ttl_seconds`
  - `temporary and not ttl_seconds` → `now + default_temporary_ttl_seconds`
  - else `None`
  Used by both `upload_proxy` and `create_presign`. Key prefix already switches on
  `expires_at is not None` (prompt 06 `_key`).
- All read paths already 410 on expiry via `service.get` (prompt 07). Double-check
  `download_url` and the public routes (prompt 09) call the same guard.
- `app/maintenance/__init__.py`
- `app/maintenance/dependencies.py` — `get_maintenance_service(db, storage) ->
  MaintenanceService`; `MaintenanceServiceDep`.
- `app/maintenance/service.py` — `@log_errors class MaintenanceService(repo,
  storage)`:
  - `purge_expired(*, namespace: str | None, older_than_seconds: int | None) ->
    PurgeResult`:
    - `cutoff = now - (older_than_seconds or 0)`
    - loop `repo.iter_expired(before=cutoff, namespace=namespace, limit=500)` until
      empty; for each: `storage.delete_object(key)` (swallow `StorageError`, log),
      `repo.hard_delete(blob)`, `repo.add_event(blob.id, blob.namespace, EXPIRED,
      detail={"key": blob.key})` — but the row is gone after hard_delete, so write
      the event **before** deleting, or keep events and only null the FK. Decision:
      write the `expired` event, then `hard_delete` the blob row (leave its events;
      make the FK `ondelete="SET NULL"` or drop the FK constraint and keep
      `blob_id` as a plain uuid column — pick one and note it in the migration).
    - accumulate `scanned`, `purged`, `bytes_reclaimed` (sum of `byte_size` for
      `stored` ones).
    - emit `TemporaryBlobsPurged` (Count=purged) + `TemporaryPurgedBytes`
      (Bytes=bytes_reclaimed), dimensioned by `namespace` when the filter was set.
- `app/maintenance/router.py` — `APIRouter(prefix="/internal/v1/maintenance",
  tags=["maintenance"], dependencies=[RequireServiceApiKey])`:
  - `POST "/purge-expired"` — query `namespace: str | None`, `older_than_seconds:
    int | None` → `PurgeResult`. (No `CallerNamespace` requirement — this is an
    operator endpoint; still behind the service key. If `namespace` query is
    omitted it purges across all namespaces.)
- `app/main.py` — `include_router(maintenance_router)`.
- Migration: if you change the `blob_events.blob_id` FK to `SET NULL` / drop it,
  autogenerate + review a revision.

## Acceptance
`tests/test_temporary.py` + `tests/test_purge.py`:
- proxy upload with `ttl_seconds=120` → `expires_at ≈ now+120`, key under `tmp/`,
  `is_temporary` true in `BlobRead`
- `temporary=true` with no ttl → `expires_at ≈ now + default`
- `ttl_seconds` over `MAX_TEMPORARY_TTL_SECONDS` ⇒ 422 (`TtlRejected`)
- freeze/patch time (or insert a row with `expires_at` in the past): `GET /{id}` ⇒
  410; `download-url` ⇒ 410; public route ⇒ 410
- `purge-expired`: seed 2 expired + 1 live; call → `{scanned:2, purged:2,
  bytes_reclaimed:N}`; live blob untouched; objects gone from the fake; re-run ⇒
  `{scanned:0, purged:0}` (idempotent)
- `namespace` filter only purges that namespace
- `TemporaryBlobsPurged` / `TemporaryPurgedBytes` emitted
- `ruff` / `mypy` / `pytest` green

## Notes
Prefer keeping `blob_events` after the blob row is hard-deleted (audit outlives the
file). Simplest: make `blob_id` a plain indexed `Uuid` column with no FK
constraint. Update spec §7.3 if you do.
