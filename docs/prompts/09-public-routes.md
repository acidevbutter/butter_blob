# Prompt 09 — Open public routes

**Status:** ✅ done.

## Goal
The unauthenticated `/v1/public/*` tree: 302-redirect to a `public` blob's bytes,
plus public metadata.

## Depends on
07.

## Reference
`docs/spec.md` §8.4, §9.2. `../butter_relay/app/messages/router.py` for router shape
(this one has **no** auth dependency).

## Files
- `app/public/__init__.py`
- `app/public/schemas.py` — `PublicMeta` (import from `app.blobs.schemas` or
  redefine): `filename`, `content_type`, `byte_size`, `created_at`, `expires_at`.
- `app/public/dependencies.py` — `get_public_service(db, storage) -> PublicService`;
  `PublicServiceDep`.
- `app/public/service.py` — `@log_errors class PublicService(repo, storage)`:
  - `resolve(namespace, public_slug) -> Blob` — `repo.get_public(namespace,
    public_slug)`; `None` ⇒ `NotFoundError` + `emit_blob_metric("PublicBlobMiss",
    namespace=namespace, Reason="not_found")`; expired ⇒ `GoneError` +
    `emit_blob_metric("PublicBlobMiss", ..., Reason="expired")` (or a dedicated
    `ExpiredBlobRequested` — pick `PublicBlobMiss` with `Reason=expired` for the
    public side, per spec §9.2).
  - `redirect_url(namespace, public_slug, *, disposition) -> str` — `resolve`,
    then `storage.generate_presigned_get(key, ttl=min(300,
    s3_presign_expires_seconds), disposition=disposition, filename=blob.filename)`;
    `emit_blob_metric("PublicBlobServed", namespace=namespace)`.
  - `meta(namespace, public_slug) -> PublicMeta` — `resolve` then project the five
    fields.
- `app/public/router.py` — `APIRouter(prefix="/v1/public", tags=["public"])` (no
  `dependencies=`):
  - `GET "/{namespace}/{public_slug}"` — `disposition: Literal["inline",
    "attachment"] = "inline"` → `RedirectResponse(url, status_code=302)`.
  - `GET "/{namespace}/{public_slug}/meta"` → `PublicMeta`.
- `app/main.py` — `include_router(public_router)`.

## Acceptance
`tests/test_public.py`:
- publish a blob (`PATCH visibility=public`), then `GET /v1/public/{ns}/{slug}` ⇒
  302 with `Location` = the fake presigned URL; `PublicBlobServed` emitted
- a `private` blob's slug ⇒ 404 (`PublicBlobMiss`, `Reason=not_found`)
- an unknown slug ⇒ 404
- an expired public blob ⇒ 410 (or 404 with `Reason=expired` — match your choice
  to spec §8.4)
- `/meta` returns exactly the five fields and no `key` / `namespace` internals
- these routes work with **no** auth headers at all
- `ruff` / `mypy` / `pytest` green

## Notes
`RedirectResponse` default is 307; pass `status_code=302` explicitly. Keep public
presign TTL short (≤ 5 min) — the redirect is followed immediately.
