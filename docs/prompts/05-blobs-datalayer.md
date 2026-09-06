# Prompt 05 — Blobs data layer (models, events, repository, schemas)

**Status:** ⬜ not started.

## Goal
`blobs` + `blob_events` tables, the repository (all queries the later prompts
need), the Pydantic schemas, and the migration. No routes.

## Depends on
02. (Land before or with 04's `usage()` query.)

## Reference
`../butter_relay/app/messages/{models,repository,schemas}.py`,
`../butter_relay/app/templates_/repository.py` (`_commit_or_raise_conflict`),
`docs/spec.md` §7.2, §7.3.

## Files
- `app/blobs/__init__.py`
- `app/blobs/models.py`:
  - `class Visibility(str, enum.Enum): PRIVATE = "private"; PUBLIC = "public"`
  - `class BlobStatus(str, enum.Enum): PENDING = "pending"; STORED = "stored"; DELETED = "deleted"`
  - `class BlobEventAction(str, enum.Enum)` — `created`, `uploaded`, `completed`,
    `updated`, `visibility_changed`, `downloaded`, `deleted`, `expired`.
  - `class Blob(Base)` — columns exactly per spec §7.2. `blob_metadata:
    Mapped[dict] = mapped_column("blob_metadata", JSON, default=dict)`.
    `__table_args__ = (UniqueConstraint("namespace", "key",
    name="uq_blob_namespace_key"),)`. `@property def is_temporary(self) -> bool:
    return self.expires_at is not None`.
  - `class BlobEvent(Base)` — `blob_id` `ForeignKey("blobs.id")` index,
    `namespace` index, `action` `String(30)`, `detail` JSON default dict, `at`
    `server_default=func.now()` index.
- `app/blobs/schemas.py`:
  - `BlobRead(ConfigDict(from_attributes=True))` — `id`, `namespace`, `filename`,
    `content_type`, `byte_size`, `original_byte_size`, `checksum_sha256`,
    `visibility`, `status`, `public_slug`, `is_temporary`, `expires_at`,
    `metadata` (`alias="blob_metadata"`, `populate_by_name=True`), `created_at`,
    `updated_at`. Add a computed `public_url` — build it in the service (needs
    `settings.public_base_url`); schema field is `str | None`.
  - `BlobEventRead(ConfigDict(from_attributes=True))` — `action`, `detail`, `at`.
  - `PresignRequest` — `filename: str`, `content_type: str`, `byte_size: int | None`,
    `visibility: Visibility = PRIVATE`, `metadata: dict = {}`, `ttl_seconds: int | None`.
  - `PresignResponse` — `blob_id: UUID`, `upload_url: str`, `method: str = "PUT"`,
    `headers: dict[str, str]`, `expires_at: datetime`.
  - `BlobPatch` — `visibility: Visibility | None`, `filename: str | None`,
    `metadata: dict | None`, `expires_at: datetime | None` (with a sentinel so
    "omitted" ≠ "set to null"; use `model_fields_set` in the service).
  - `DownloadUrlResponse` — `url: str`, `expires_at: datetime`.
  - `PurgeResult` — `scanned: int`, `purged: int`, `bytes_reclaimed: int`.
  - `PublicMeta` — `filename`, `content_type`, `byte_size`, `created_at`, `expires_at`.
- `app/blobs/repository.py` — `BlobRepository(session)`:
  - `create(blob) -> Blob` (via `_commit_or_raise_conflict` covering
    `uq_blob_namespace_key` and `public_slug`)
  - `get(blob_id) -> Blob | None` (`session.get`)
  - `get_for_namespace(blob_id, namespace) -> Blob | None` (get + namespace match,
    else `None`)
  - `get_public(namespace, public_slug) -> Blob | None` (visibility=public,
    status=stored)
  - `list(namespace, *, visibility=None, status=None, checksum=None,
    temporary=None, expired=None, created_after=None, created_before=None,
    limit=100) -> list[Blob]` — ordered `created_at DESC`; `expired` compares
    `expires_at` to `func.now()`.
  - `update(blob) -> Blob`, `soft_delete(blob) -> Blob`, `hard_delete(blob) -> None`
  - `add_event(blob_id, namespace, action, detail=None) -> BlobEvent`
  - `list_events(blob_id) -> list[BlobEvent]` (newest first)
  - `sum_stored_bytes(namespace) -> int` (`COALESCE(SUM(byte_size),0)` where
    `namespace=? AND status='stored'`)
  - `iter_expired(before: datetime, namespace: str | None = None, limit: int =
    500) -> list[Blob]`
  - `_commit_or_raise_conflict(detail_prefix)` helper.
- `app/db/all_models.py` — add `from app.blobs import models as blobs_models  # noqa: F401`.
- `alembic/versions/*_blobs.py` — autogenerate, review (FK, indexes, unique),
  commit. If 04's migration already ran, this is a second revision chained after it.

## Acceptance
`tests/test_blobs_repository.py` (service-layer style, uses `db_session`):
- create → get → `get_for_namespace` (hit + cross-namespace miss)
- `list` filters: `status`, `visibility`, `checksum`, `temporary`, `expired`,
  `limit`, ordering
- `sum_stored_bytes` ignores `pending`/`deleted`
- `iter_expired` returns only rows past `expires_at`
- duplicate `(namespace, key)` ⇒ `ConflictError`; duplicate `public_slug` ⇒ `ConflictError`
- `add_event` / `list_events` newest-first
- `ruff` / `mypy` / `pytest` green

## Notes
Keep `BlobRead.public_url` out of the ORM — the service fills it. `expires_at`
comparisons: use timezone-aware `datetime.now(UTC)` in the repo, `func.now()` in
SQL; sqlite stores naive — normalize in the model or compare via SQL only.
