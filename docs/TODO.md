# butter_blob — TODO

Ordered by prompt. Tick a box when it's done **and** its acceptance passes
(`pytest` + `ruff` + `mypy`, plus the prompt's manual check). See
[`prompts/`](prompts/) for the detail and [`spec.md`](spec.md) for the contract.

---

## 00 — Scaffold & tooling — Status: ✅ done
- [x] `pyproject.toml` (Poetry, py3.12, deps, ruff/mypy/pytest config)
- [x] `Dockerfile` (py3.12-slim, non-root, entrypoint) + `docker-entrypoint.sh`
- [x] `docker-compose.yml` (`api` :8003, `devbutter_shared` alias `blob-api`)
- [x] `.env.example` (all settings + `AWS_*` + `AWS_EMF_*`)
- [x] `.gitignore`, `app/` + `tests/` package tree, `README.md` skeleton
- [x] branch renamed `main` → `master`
- [x] **Acceptance:** `ruff` clean, `pytest` exits 0, `docker compose config` valid

## 01 — Settings, logging, middleware, core, main — Status: ✅ done
- [x] `app/settings/{config,logging_config,middleware}.py`
- [x] `app/core/decorators.py` (typed `log_call` / `log_errors`)
- [x] `app/core/exceptions.py` (registry + `DomainError` subclasses incl. 415/413/507/410/502)
- [x] `app/core/metrics.py` (`DevButter/ButterBlob`) + `app/core/observability.py`
- [x] `app/core/dependencies.py` (`DbSession`, `RequireServiceApiKey`, `RequireAdminApiKey`, `CallerNamespace`)
- [x] `app/main.py` wiring + `/health` + `/health/ready` + `/` → `/docs`
- [x] **Acceptance:** `test_health`, `test_auth`, `test_decorators` green; `ruff`/`mypy` clean

## 02 — Async DB layer & Alembic — Status: ✅ done
- [x] `app/db/{base,session,all_models}.py`
- [x] `alembic.ini` + async `alembic/env.py` + `script.py.mako` + `versions/.gitkeep`
- [x] `tests/conftest.py` (sqlite `db_session`, `client`, `blob_storage`, `internal_headers`, `admin_headers`, `_settings_override`)
- [x] **Acceptance:** `alembic upgrade head` wiring works; `pytest`/`mypy`/`ruff` clean

## 03 — Storage layer — Status: ✅ done
- [x] `app/core/storage.py` (`BlobStorage`, `HeadObject`, `get_blob_storage`, `BlobStorageDep`)
- [x] `tests/fakes.py` `InMemoryBlobStorage`
- [x] `/health/ready` calls `bucket_exists()`
- [x] **Acceptance:** `test_storage` (fake round-trip, moto real round-trip, `ClientError` → `StorageError` + metric)

---

## 04 — Namespaces domain + admin limit routes — Status: ✅ done
- [x] `app/namespaces/{models,schemas,repository,service,router,dependencies}.py`
- [x] `Namespace` model with the six limit columns
- [x] `app/admin/{router,dependencies}.py` — `GET/POST /admin/v1/namespaces`, `PUT .../{slug}/limits`
- [x] `/internal/v1/namespaces/{slug}` `GET` + `PATCH` (own only)
- [x] `get_caller_namespace` upserts via `NamespaceService.resolve_caller`
- [x] `all_models.py` import + migration (reviewed)
- [x] **Acceptance:** `test_namespaces` + `test_admin_namespaces` (auto-upsert, dup slug 409, limit validation, admin gate, cross-namespace 404)

## 05 — Blobs data layer — Status: ✅ done
- [x] `app/blobs/{models,schemas,repository}.py` (`Blob`, `BlobEvent`, enums)
- [x] repository: CRUD, `list` filters, `sum_stored_bytes`, `iter_expired`, events, `_commit_or_raise_conflict`
- [x] `all_models.py` import + migration (FK, indexes, `uq_blob_namespace_key`)
- [x] **Acceptance:** `test_blobs_repository` (filters, ordering, conflicts, events, sum, expired)

## 06 — Blob upload: proxy + presigned + complete — Status: ✅ done
- [x] `app/core/imaging.py` (`transform`)
- [x] `app/blobs/{service,router,dependencies}.py` — `POST /internal/v1/blobs`, `/presign`, `/{id}/complete`
- [x] enforcement ladder (415 / 413 / 507 / 422) with metrics
- [x] compression pipeline (proxy inline; `complete` download-transform-reput)
- [x] `all_models` wired, router included
- [x] **Acceptance:** `test_blobs_upload` + `test_imaging` (happy paths, every rejection, compression ratio, complete-409)

## 07 — Blob manage: list / get / download-url / events / patch / delete — Status: ⏳ implemented, coverage pending
- [x] service + router additions
- [x] owner-scoping on every verb; 410 on expired reads
- [x] `public_slug` allocation on visibility→public (retry on conflict)
- [x] metadata shallow-merge; TTL extend/clear capped
- [x] soft + hard delete; best-effort S3 delete
- [ ] **Acceptance:** ampliar `test_blobs_manage` para delete hard e asserções de métricas.

## 08 — Temporary files & purge-expired — Status: ✅ done
- [ ] `_resolve_expiry` shared by both upload paths; `tmp/` key prefix
- [ ] 410 on every expired read path
- [ ] `app/maintenance/{router,service,dependencies}.py` — `POST /internal/v1/maintenance/purge-expired`
- [ ] `blob_events` retained after hard-delete (drop/relax the FK) + migration
- [ ] **Acceptance:** `test_temporary` + `test_purge` (ttl set, over-cap 422, expired 410, purge counts, idempotent, namespace filter, metrics)

## 09 — Open public routes — Status: ✅ done
- [x] `app/public/{router,schemas,service,dependencies}.py` (no auth)
- [x] `GET /v1/public/{ns}/{slug}` → 302; `/meta` → JSON
- [x] `PublicBlobServed` / `PublicBlobMiss` metrics
- [x] **Acceptance:** `test_public` (302 to fake URL, private 404, unknown 404, expired 410/gone, `/meta` shape, no-auth)

## 10 — Infra wiring (`infra/`) — Status: ⏳ pending integrated smoke
- [x] `blob` DB in `postgres/init/001-create-databases.sh` + `infra/.env(.example)`
- [x] `minio` + `createbuckets` services + `minio_data` volume in `infra/docker-compose.yml`
- [x] `infra/README.md` / `infra/CHANGELOG.md` notes
- [ ] **Acceptance:** compose config valid; o boot integrado e `/health/ready` ainda dependem de subir o ambiente.

## 11 — Docs finalization & smoke test — Status: ⬜ not started
- [ ] full `README.md` (relay heading tree)
- [ ] `CHANGELOG.md` + `RELEASE_NOTES.md` (pt-BR)
- [ ] `scripts/curl_smoke_test.sh`
- [ ] `docs/producer-contract.md` + `docs/terraform-notes.md`
- [ ] **Acceptance:** smoke script passes against a running stack; env table matches config

---

## 12 — Per-namespace DB-backed bearer API keys — Status: ✅ done · Codex
- [x] `app/api_keys/*` (hashed `bbk_` keys, mint/revoke, `CurrentApiKey`)
- [x] admin key-management routes under `/admin/v1/namespaces/{slug}/keys`
- [x] `CallerNamespace` resolution: bearer key → header fallback (`allow_header_namespace`)
- [x] migration + spec/`.env` updates
- [x] **Acceptance:** `test_api_keys` (mint/auth/revoke, bearer identity, header fallback toggle, admin gate)

## 13 — Async post-processing worker — Status: ✅ done · Codex
- [x] `app/worker/*` + `app/core/jobs.py` (enqueue on `stored`)
- [x] handlers: `virus_scan` (clamd), `image_thumbnail` (Pillow sidecars), `video_transcode` (stub)
- [x] `status=processing`, `blob_events` `processing`/`processed`/`quarantined` + migration
- [x] `worker` + `redis` compose services (Celery broker/backend; ElasticMQ/SQS foi removido)
- [x] **Acceptance:** `test_worker` (enqueue, thumbnail sidecars, quarantine, retry-on-failure, no-op when unconfigured)

## 14 — `devbutter_backend` client — Status: ✅ done · Codex · edits `../devbutter_backend`
- [x] `app/core/clients/butter_blob_client.py` (mirror `butter_mind_client`)
- [x] config block + `.env(.example)` + `lifespan` close (`close_butter_blob_client`)
- [x] **Acceptance:** `tests/test_butter_blob_client.py` (round-trip mock + both headers,
      404/413/507 → `UpstreamServiceError` w/ status, `download_url` url field,
      `emit_metrics` `UpstreamService="butter_blob"`, missing-key guard before HTTP);
      `ruff` + `pytest` green (repo `mypy` pre-existing dirty, no new errors)

## 15 — CDN / custom domain for `/v1/public/*` — Status: ✅ done · Codex · edits `../infra`
- [x] Terraform: `../infra/terraform/staging/cdn_blob.tf` — CloudFront + OAC + cache
      policy + ACM (us-east-1) + Route53 + private-bucket OAC policy (`validate`/`fmt` clean)
- [x] `public_cdn_base_url` / `cloudfront_distribution_id` settings; CDN URLs for
      permanent public blobs (`redirect_url` + `BlobRead.public_url`); `Cache-Control`
      `public, max-age=86400` (permanent) / `no-store` (temporary) on `302` + `/meta`
- [x] direct public upload now allocates a `public_slug` (proxy + presign paths)
- [x] `app/core/cdn.py::invalidate` on delete / visibility→private / content replace
- [x] `docs/spec.md` §8.4 (decision B) + §10, `docs/terraform-notes.md`, `.env.example`
- [x] **Acceptance:** `test_public` + `test_blobs_manage` CDN cases green; `ruff`/`mypy`
      green. `terraform plan` still needs the `devbutter-nonprod` SSO profile + live zone.

## 16 — HTML admin dashboard — Status: ✅ done · Codex
- [x] `SessionMiddleware` + `admin_users` (bcrypt) + `SessionRequiredError`
- [x] `app/adminui/*` — login, namespace list, limits form, blob browser + events
- [x] migration; JSON `/admin/v1/*` unchanged
- [x] **Acceptance:** `test_adminui` (login gate 303, limits form ↔ JSON API, blob table/detail/soft-delete)
