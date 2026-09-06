# Prompt 01 — Settings, logging, middleware, core, main wiring

**Status:** ✅ done.

## Goal
The framework layer: config, logging, request middleware, the exception registry,
EMF metrics, the observability helper, the cross-domain dependencies, and `main.py`
wired in relay order.

## Depends on
00.

## Reference
`../butter_relay/app/settings/{config,logging_config,middleware}.py`,
`../butter_relay/app/core/{decorators,exceptions,metrics}.py`,
`../butter_relay/app/main.py`, `../butter_mind/app/core/dependencies.py`
(the `X-*-Api-Key` header guards).

## Files
- `app/settings/config.py` — `Settings(BaseSettings)` with the fields in
  `docs/spec.md` §10; module-level `settings = Settings()`;
  `SettingsConfigDict(env_file=".env", extra="ignore")`.
- `app/settings/logging_config.py` — relay verbatim; also quiet `boto3` to WARNING.
- `app/settings/middleware.py` — `RequestContextMiddleware` only (no
  `SessionMiddleware`): request id on `request.state`, timing, one `app.request`
  log line, `X-Request-ID` header, EMF `RequestCount`/`Latency`/`4xx`/`5xxCount`
  with dims `Method`/`Route`/`StatusClass`. `register_middleware(app)`.
- `app/core/decorators.py` — `log_call` / `log_errors`, typed with a `TypeVar`
  (`F` bound `Callable`, `C` bound `type`) + `cast` so `mypy --strict` is clean
  (the fastapi-builder skill says add the typing back when the project is strict).
- `app/core/exceptions.py` — registry (`exception_handler`,
  `register_exception_handlers`). `DomainError` base with `status_code` +
  `default_detail`; subclasses `NotFoundError` 404, `ConflictError` 409,
  `UnauthorizedError` 401, `ForbiddenError` 403, `ValidationFailedError` 422,
  `UnsupportedMediaTypeError` 415, `PayloadTooLargeError` 413,
  `QuotaExceededError` 507, `GoneError` 410, `StorageError` 502. One generated
  handler per subclass returning `{"detail": ...}`.
- `app/core/metrics.py` — relay clone; `NAMESPACE="DevButter/ButterBlob"`,
  `SERVICE_NAME="butter-blob"`, `LOG_GROUP_NAME="/ecs/devbutter/staging/blob"`;
  keep `emit_metrics(metrics, dimensions=None)`, `route_template`, `status_class`,
  `configure_metrics()`.
- `app/core/observability.py` — `emit_blob_metric(name, value=1, unit="Count", *,
  namespace=None, **dimensions)` and `emit_blob_metrics(list[Metric], *,
  namespace=None, **dimensions)`; both delegate to `emit_metrics`, adding
  `Namespace` when given.
- `app/core/dependencies.py` — `DbSession`; `require_service_api_key` /
  `require_admin_api_key` (header compare vs settings; fail ⇒ `NotFoundError` +
  `AuthFailure` metric with `Reason`); `RequireServiceApiKey` /
  `RequireAdminApiKey` as `Depends(...)` objects for `dependencies=[...]`;
  `normalize_namespace(raw)` (slugify to `[a-z0-9_-]`); `get_caller_namespace`
  (header `X-Blob-Namespace`; blank ⇒ `ValidationFailedError`; returns the
  normalized slug) + `CallerNamespace` alias. **Prompt 04 replaces
  `get_caller_namespace`'s body with `NamespaceService.resolve_caller`.**
- `app/main.py` — `setup_logging(settings.log_level)` → `configure_metrics()` →
  `FastAPI(title="Butter Blob", description=...)` → `register_middleware` →
  `register_exception_handlers` → `GET /health` → `GET /health/ready`
  (`db: DbSession`, `storage: BlobStorageDep`; DB `SELECT 1` + `storage.bucket_exists()`;
  503 + `HealthCheckFailure` with `Check`) → `GET /` → `RedirectResponse("/docs")`.

## Acceptance
- `tests/test_health.py` — `/health` 200; `/health/ready` 200 (sqlite + fake storage);
  503 when the fake bucket is absent; `/` → 307 to `/docs`.
- `tests/test_auth.py` — throwaway `/_probe/internal` + `/_probe/admin` routes wired
  to the guards: no/wrong service key ⇒ 404; missing `X-Blob-Namespace` ⇒ 422;
  ok ⇒ 200 with normalized namespace (`Crate Diggr` → `crate-diggr`,
  `devbutter_backend` unchanged); admin key gate.
- `tests/test_decorators.py` — relay's suite (sync/async `log_call`, `extra` fields,
  `log_errors` skips dunder/private).
- `ruff check .` + `mypy .` clean.

## Notes
`get_caller_namespace` currently only normalizes + returns; the `namespaces` row
upsert lands in prompt 04. `/health/ready` is dependency-injected (not
`session_factory` direct) so the sqlite + fake-storage overrides apply in tests.
