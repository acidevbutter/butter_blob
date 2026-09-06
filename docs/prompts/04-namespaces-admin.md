# Prompt 04 — Namespaces domain + admin limit routes

**Status:** ⬜ not started.

## Goal
The `namespaces` table (registry + per-namespace limits), its self-service
`/internal/v1/namespaces` routes, the admin `/admin/v1/*` limit-management routes,
and wiring `CallerNamespace` to upsert-on-first-use.

## Depends on
02, 03.

## Reference
`../butter_relay/app/projects/*` (a full domain with a `slug`, `_commit_or_raise_conflict`),
`../butter_relay/app/api_keys/dependencies.py` (a domain that also owns a dependency),
`docs/spec.md` §4, §5, §7.1, §8.2, §8.3.

## Files
- `app/namespaces/__init__.py`
- `app/namespaces/models.py` — `class Namespace(Base)`:
  - `id` uuid pk (`default=uuid.uuid4`)
  - `slug` `Mapped[str] = mapped_column(String(100), unique=True, index=True)`
  - `name` `Mapped[str] = mapped_column(String(200), default="")`
  - `description` `Mapped[str | None] = mapped_column(Text, default=None)`
  - `max_storage_bytes` `Mapped[int | None] = mapped_column(BigInteger, default=None)`
  - `max_file_bytes` `Mapped[int | None] = mapped_column(BigInteger, default=None)`
  - `allowed_content_types` `Mapped[list[str] | None] = mapped_column(JSON, default=None)`
  - `allowed_extensions` `Mapped[list[str] | None] = mapped_column(JSON, default=None)`
  - `image_compression_quality` `Mapped[int | None] = mapped_column(SmallInteger, default=None)`
  - `image_max_dimension` `Mapped[int | None] = mapped_column(Integer, default=None)`
  - `created_at` (`server_default=func.now()`), `updated_at`
    (`server_default=func.now(), onupdate=func.now()`)
- `app/namespaces/schemas.py`:
  - `NamespaceRead` (`ConfigDict(from_attributes=True)`): `slug`, `name`,
    `description`, all six limit fields, `created_at`, `updated_at`.
  - `NamespaceUsageRead(NamespaceRead)`: `+ blob_count: int`, `total_bytes: int`,
    `temporary_count: int`.
  - `NamespaceSelfUpdate`: `name: str | None`, `description: str | None`.
  - `NamespaceLimitsUpdate`: all six limit fields `| None`, all default `None`.
    Validators: `image_compression_quality` in `1..100`; byte caps `>= 0`;
    `allowed_content_types` / `allowed_extensions` lowercased, stripped,
    de-duplicated, extensions forced to a leading `.`. Use
    `model_config = ConfigDict(extra="forbid")`.
  - `NamespaceCreate(NamespaceLimitsUpdate)`: `+ slug: str`, `name: str = ""`,
    `description: str | None = None`.
- `app/namespaces/repository.py` — `NamespaceRepository(session)`:
  - `get_by_slug(slug) -> Namespace | None`
  - `create(namespace: Namespace) -> Namespace` (+ `_commit_or_raise_conflict`)
  - `upsert(slug) -> Namespace` — get or insert a bare row (race-safe: on
    `IntegrityError` re-`get_by_slug`).
  - `update(namespace) -> Namespace`
  - `list_all() -> list[Namespace]`
  - `usage(slug) -> tuple[int, int, int]` — `(count, sum(byte_size), count where
    expires_at is not None)` over `blobs` filtered `status='stored'`. Import the
    `Blob` model lazily or via `app.blobs.models` (this creates a soft dependency
    on prompt 05 — acceptable; guard with a "table missing" fallback returning
    zeros until 05 lands, or land 05 first).
- `app/namespaces/service.py` — `@log_errors class NamespaceService`:
  - `resolve_caller(slug) -> Namespace` — `repository.upsert(slug)`.
  - `get(slug) -> Namespace` — 404 if missing.
  - `get_usage(slug) -> NamespaceUsageRead` — `get` + `repository.usage`.
  - `list_with_usage() -> list[NamespaceUsageRead]`.
  - `create(payload: NamespaceCreate) -> Namespace`.
  - `set_limits(slug, payload: NamespaceLimitsUpdate) -> Namespace` — `get` then
    apply `payload.model_dump(exclude_unset=True)` (so an omitted field is
    unchanged; an explicit `null` clears).
  - `update_self(slug, payload: NamespaceSelfUpdate) -> Namespace`.
- `app/namespaces/dependencies.py` — `get_namespace_service(db: DbSession) ->
  NamespaceService`; `NamespaceServiceDep = Annotated[...]`.
- `app/namespaces/router.py` — `APIRouter(prefix="/internal/v1/namespaces",
  tags=["namespaces"], dependencies=[RequireServiceApiKey])`:
  - `GET /{slug}` → `NamespaceUsageRead`. `if slug != caller: raise NotFoundError`.
  - `PATCH /{slug}` → `NamespaceRead`. Same owner check. Body `NamespaceSelfUpdate`.
- `app/admin/__init__.py`, `app/admin/dependencies.py` (nothing domain-specific;
  reuses `NamespaceServiceDep`), `app/admin/router.py` —
  `APIRouter(prefix="/admin/v1", tags=["admin"], dependencies=[RequireAdminApiKey])`:
  - `GET /namespaces` → `list[NamespaceUsageRead]`.
  - `GET /namespaces/{slug}` → `NamespaceUsageRead` (404 if unknown).
  - `POST /namespaces` → `201 NamespaceRead` (409 on dup slug).
  - `PUT /namespaces/{slug}/limits` → `NamespaceRead` (404 if unknown). Body
    `NamespaceLimitsUpdate`.
- `app/core/dependencies.py` — replace `get_caller_namespace` body:
  normalize the header, then `NamespaceService(NamespaceRepository(db)).resolve_caller(slug)`
  and `return namespace.slug`. It now needs `db: DbSession`. Keep raising
  `ValidationFailedError` on a blank header.
- `app/db/all_models.py` — add `from app.namespaces import models as namespaces_models  # noqa: F401`.
- `app/main.py` — `include_router(namespaces_router)` and `include_router(admin_router)`.
- `alembic/versions/*_namespaces.py` — `alembic revision --autogenerate -m
  "namespaces"`, review, commit.

## Acceptance
`tests/test_namespaces.py` + `tests/test_admin_namespaces.py`:
- First `/internal/v1/*` call with a new `X-Blob-Namespace` auto-creates the row
  (assert via `GET /internal/v1/namespaces/{slug}`).
- `GET`/`PATCH /internal/v1/namespaces/{other}` ⇒ 404.
- `POST /admin/v1/namespaces` twice with the same slug ⇒ 201 then 409.
- `PUT /admin/v1/namespaces/{slug}/limits` sets values; `GET` reads them back;
  `image_compression_quality=0` or `101` ⇒ 422; extensions normalized to `.ext`.
- `/admin/v1/*` without `X-Admin-Api-Key` ⇒ 404.
- `ruff` / `mypy` / `pytest` green.

## Notes
`resolve_caller` upsert must be race-safe (two concurrent first-calls). The
`usage()` query depends on `blobs`; either land prompt 05 first or ship `usage()`
returning zeros when the table/model is absent and tighten it in 05.
