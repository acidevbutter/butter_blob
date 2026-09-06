# Prompt 11 — Docs finalization & smoke test

**Status:** ⬜ not started.

## Goal
Ship the operator-facing docs and an end-to-end smoke script.

## Depends on
04–10.

## Reference
`../butter_relay/README.md` (heading tree), `../butter_relay/CHANGELOG.md` +
`../butter_relay/RELEASE_NOTES.md` (pt-BR format),
`../butter_relay/scripts/curl_smoke_test.sh`.

## Files
- `README.md` — expand to the full `butter_relay` heading tree, adapted:
  `# Butter Blob` → `## Architecture` (embed the spec's component + one sequence
  diagram) → `### Blob lifecycle` → `## Tech stack` (table) → `## Project structure`
  (tree + the 6-file domain note) → `## Step-by-step: run it locally` (1
  Prerequisites, 2 Configure env, 3 Bring up infra, 4 Create the blob DB, 5 Bring
  up the service, 6 Upload a file, 7 Run the tests, 8 Run the smoke test) →
  `## Environment variables` (table, from spec §10) → `## Namespace & limits`
  (how an admin configures a caller) → `## Consuming from another service`
  (link to `docs/producer-contract.md`) → `## Deploying to AWS (shape, not IaC)` →
  `## Roadmap notes` (prompts 12–16).
- `CHANGELOG.md` — pt-BR, Keep-a-Changelog. `## [0.1.0]` with `### Adicionado`
  listing the phase-1 capability set, `### Commits incluídos`.
- `RELEASE_NOTES.md` — pt-BR, `# Release Notes — Butter Blob 0.1.0`, bold
  `Data` / `Base` / `Tag` lines, `## Resumo` / `## Incluído` / `## Notas
  operacionais`.
- `scripts/curl_smoke_test.sh` — `set -euo pipefail`, `BASE_URL=${BASE_URL:-http://localhost:8003}`,
  `SERVICE_API_KEY` / `ADMIN_API_KEY` / `NS` from env. Steps, counting pass/fail:
  1. `GET /health` and `/health/ready`
  2. `PUT /admin/v1/namespaces/$NS/limits` (set a small quota + allowed formats) —
     `POST /admin/v1/namespaces` first if needed
  3. `POST /internal/v1/blobs/presign` → capture `blob_id` + `upload_url`
  4. `curl -X PUT --upload-file` a local test file to `upload_url`
  5. `POST /internal/v1/blobs/$blob_id/complete`
  6. `GET /internal/v1/blobs/$blob_id/download-url` → `curl` the URL, compare bytes
  7. `PATCH /internal/v1/blobs/$blob_id` `{"visibility":"public"}` → capture `public_slug`
  8. `GET /v1/public/$NS/$public_slug` (`-o /dev/null -w '%{http_code}'` = 302)
  9. proxy upload `POST /internal/v1/blobs` with `ttl_seconds=2`; sleep 3;
     `GET /internal/v1/blobs/$id` = 410
  10. `POST /internal/v1/maintenance/purge-expired` → prints `purged`
  11. `GET /docs` = 200
  Exit non-zero on any mismatch; print a tally.
- `docs/producer-contract.md` — for a consuming service: base URL / alias
  (`http://blob-api:8000`), the two headers, each request/response shape it will
  use (`presign`, `complete`, `download-url`, `public` URL, `delete`), the error
  codes it must handle (404/409/413/415/507/410), and a short httpx example.
- `docs/terraform-notes.md` — staging changes (not applied here): add `butter-blob`
  to the enumerated ECR / log-group (`/ecs/devbutter/staging/blob`) / task-role /
  Secrets (`/devbutter/staging/butter-blob`) lists in
  `infra/terraform/staging/main.tf`; new `aws_s3_bucket` (SSE, public-access-block,
  versioning, lifecycle rule `expiration`/`prefix = "tmp/"`); task-role
  `aws_iam_role_policy` for `s3:GetObject`/`PutObject`/`DeleteObject`/`ListBucket`
  on that bucket ARN; an `aws_scheduler_schedule` (EventBridge) hitting
  `POST /internal/v1/maintenance/purge-expired` daily with the service key from
  Secrets.

## Acceptance
- `bash -n scripts/curl_smoke_test.sh` ok; the script passes against a running
  `docker compose up` stack (infra + service).
- `README.md` renders; internal links resolve; env-var table matches
  `app/settings/config.py`.
- `docs/TODO.md` — 00–11 all checked.

## Notes
Keep CHANGELOG / RELEASE_NOTES pt-BR (house style). Everything else English.
