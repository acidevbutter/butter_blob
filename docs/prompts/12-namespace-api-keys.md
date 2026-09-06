# Prompt 12 — Per-namespace DB-backed bearer API keys (relay-style)

**Status:** ⬜ not started · **Runner:** Codex · **Phase:** 2.

## Goal
Give each namespace its own revocable bearer keys, so callers stop sharing one
`SERVICE_API_KEY` and identity is proven by the key, not a self-declared header.

## Depends on
04 (namespaces), 07 (blobs).

## Reference
`../butter_relay/app/api_keys/*` — the whole domain: `bbk_`-style prefix, SHA-256
hash stored, plaintext returned once, `authenticate()` + `touch_last_used()`,
`Authorization: Bearer` dependency. `docs/spec.md` §4.

## Files
- `app/api_keys/{__init__,models,schemas,repository,service,router,dependencies}.py`
  - `ApiKey` model: `id` uuid pk · `namespace` `String(100)` index · `key_hash`
    `String(64)` unique index · `prefix` `String(8)` (`"bbk_"`) · `label`
    `String(200)` · `last_used_at` `DateTime(tz)` null · `revoked_at`
    `DateTime(tz)` null · `created_at`.
  - `service`: `_KEY_PREFIX = "bbk_"`; `_hash(plain) = sha256(plain).hexdigest()`;
    `create(namespace, label) -> tuple[ApiKey, str]` (`plain = _KEY_PREFIX +
    secrets.token_urlsafe(32)`, store hash only, return plaintext once);
    `authenticate(plain) -> ApiKey` (hash lookup → reject `None` / `revoked_at` →
    `touch_last_used`); `list(namespace)`; `revoke(namespace, key_id)`.
  - `dependencies`: `get_current_api_key(db, authorization: Header) -> ApiKey` —
    parse `Bearer `, `service.authenticate`; `CurrentApiKey = Annotated[ApiKey,
    Depends(...)]`.
  - `router`: nested under admin — `APIRouter(prefix="/admin/v1/namespaces/{slug}/keys",
    tags=["api-keys"], dependencies=[RequireAdminApiKey])`: `GET ""` list (no
    plaintext), `POST ""` mint (returns `{id,label,prefix,plaintext_key}`),
    `POST "/{key_id}/revoke"`.
- `app/core/dependencies.py` — new resolution order for `/internal/v1/*` identity:
  1. if `Authorization: Bearer bbk_…` present → `CurrentApiKey`; `namespace =
     key.namespace` (the `X-Blob-Namespace` header, if also present, must match or
     ⇒ 403 `ForbiddenError`).
  2. else if `settings.allow_header_namespace` (new setting, default `True`) → the
     current `X-Service-Api-Key` + `X-Blob-Namespace` path (deprecation window).
  3. else ⇒ 404.
  Expose a single `CallerNamespace` that yields the resolved slug either way, plus
  a `CallerContext` object (`namespace`, `api_key_id | None`) for audit `detail`.
- `app/settings/config.py` — `allow_header_namespace: bool = True`. `.env.example`
  + `docs/spec.md` §4/§10 updated.
- `app/db/all_models.py` — add the import. Migration: autogenerate + review.

## Acceptance
`tests/test_api_keys.py`:
- mint → `authenticate(plain)` returns the key, sets `last_used_at`
- `revoke` → subsequent `authenticate` ⇒ `UnauthorizedError` (401)
- an `/internal/v1/blobs` call with `Authorization: Bearer <key>` and **no**
  `X-Blob-Namespace` works and is owned by the key's namespace
- bearer + mismatched `X-Blob-Namespace` ⇒ 403
- header-only path still works while `allow_header_namespace=True`; flip it off →
  header-only ⇒ 404
- `/admin/v1/namespaces/{slug}/keys` CRUD; non-admin ⇒ 404
- `blob_events.detail` records `api_key_id` when a bearer key was used
- `ruff` / `mypy` / `pytest` green

## Notes
Don't remove the header path in this prompt — just make it optional and defaulted
on. A later cleanup flips the default and eventually deletes it.
