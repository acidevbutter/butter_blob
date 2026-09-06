# Prompt 14 — `devbutter_backend` client for butter_blob

**Status:** ⬜ not started · **Runner:** Codex · **Phase:** 2 · **Edits:** `../devbutter_backend`.

## Goal
A first-class client in `devbutter_backend` so its code uploads/serves files
through butter_blob the same way it already talks to `butter_mind`.

## Depends on
06, 07, 09 (the endpoints it calls).

## Reference
`../devbutter_backend/app/core/clients/butter_mind_client.py` — the exact pattern
to mirror: `httpx.AsyncClient(base_url=..., timeout=...)`, `@log_call` methods,
non-2xx ⇒ `UpstreamServiceError(status_code=...)`, EMF
`UpstreamCallCount`/`UpstreamLatency`/`UpstreamErrorCount` with
`{"UpstreamService": ..., "Operation": ..., "StatusClass": ...}`, module singleton
+ `close_*` called from `lifespan`. `../devbutter_backend/app/settings/config.py`
for the `*_base_url` / `*_timeout` / `*_api_key` block. `docs/producer-contract.md`.

## Files (under `../devbutter_backend/`)
- `app/settings/config.py` — add:
  `butter_blob_base_url: str = "http://blob-api:8000"`,
  `butter_blob_request_timeout_seconds: float = 30.0`,
  `butter_blob_service_api_key: str = ""`,
  `butter_blob_namespace: str = "devbutter_backend"`.
  `.env` + `.env.example` updated.
- `app/core/clients/butter_blob_client.py` — `class ButterBlobClient`:
  - `__init__` builds the `AsyncClient`; `_headers()` → `{"X-Service-Api-Key":
    settings.butter_blob_service_api_key, "X-Blob-Namespace":
    settings.butter_blob_namespace}` (raise `UpstreamServiceError` if the key is
    unset).
  - `_request(method, path, **kw)` — timing, `emit_metrics` (`UpstreamService=
    "butter_blob"`), non-2xx ⇒ `UpstreamServiceError`.
  - methods: `presign_upload(filename, content_type, *, visibility="private",
    byte_size=None, ttl_seconds=None) -> dict`, `complete_upload(blob_id) -> dict`,
    `upload_bytes(filename, data, content_type, **opts) -> dict` (multipart proxy),
    `get_blob(blob_id) -> dict`, `download_url(blob_id, *, expires_in=300,
    disposition="attachment") -> str`, `delete_blob(blob_id, *, hard=False) ->
    None`, `public_url(namespace, public_slug) -> str` (pure string build from
    `butter_blob_base_url`).
  - `get_butter_blob_client()` singleton + `close_butter_blob_client()`.
- `app/main.py` (devbutter_backend) — `close_butter_blob_client()` in the
  `lifespan` shutdown alongside the existing client closers.
- `docker-compose.yml` (devbutter_backend) — ensure it's on `devbutter_shared` so
  `blob-api` resolves (it already is for `mind-api`).

## Acceptance
`tests/` in devbutter_backend (`respx` / httpx mock):
- `presign_upload` → returns the parsed body; sends both headers
- non-2xx (404/413/507) ⇒ `UpstreamServiceError` with the status code
- `download_url` returns the `url` field
- `emit_metrics` called with `UpstreamService="butter_blob"` and the operation
- missing `butter_blob_service_api_key` ⇒ `UpstreamServiceError` before any HTTP
- `ruff` / `mypy` / `pytest` green in devbutter_backend

## Notes
This prompt does not change butter_blob. Keep the client thin — no ret/caching
beyond what `butter_mind_client` does (a single 502 retry is fine to mirror if
that client has one).
