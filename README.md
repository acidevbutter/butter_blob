# Butter Blob

DevButter's company-wide blob store. One service that stores and serves the files
(blobs) created or uploaded by any DevButter app or API, backed by S3 (MinIO in
local dev).

- **Namespace-bound** — every blob has a UUID and belongs to the API that created
  it (its `namespace`). Cross-namespace access 404s.
- **Two upload paths** — direct multipart proxy upload, or a presigned S3 PUT the
  caller confirms with `/complete`.
- **Admin-controlled limits** — per-namespace storage quota, max file size,
  allowed formats, and an image-compression quality/size.
- **Permanent or temporary** — a `ttl_seconds` on upload makes the blob
  auto-expire; expired reads return `410` and a purge job reclaims the space.
- **Audited** — every create / upload / update / download / delete is recorded in
  `blob_events`.
- **Observed** — request-level and file-level CloudWatch EMF metrics
  (`DevButter/ButterBlob`).

> **Status:** foundation only (prompts 00–03). Settings, logging, middleware,
> `core/` (decorators, exceptions, metrics, storage), the async DB layer and
> Alembic are in place and the service boots with `/health`, `/health/ready` and
> `/docs`. The domain routes (`blobs`, `namespaces`, `admin`, `maintenance`,
> `public`) are built by `docs/prompts/04-*.md` onward. See
> [`docs/spec.md`](docs/spec.md) for the full design and
> [`docs/TODO.md`](docs/TODO.md) for progress.

## Architecture

See [`docs/spec.md`](docs/spec.md) — component diagram, upload/download
sequences, blob lifecycle, and the data model.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web | FastAPI + Uvicorn |
| Data | PostgreSQL (shared cluster, `blob` DB) via async SQLAlchemy 2.0 + Alembic |
| Objects | S3 / MinIO via boto3 (behind `app/core/storage.py`) |
| Schemas | Pydantic v2 |
| Images | Pillow |
| Metrics | CloudWatch EMF (`aws-embedded-metrics`) |
| Packaging | Poetry |
| Lint / types | Ruff, mypy (strict) |
| Tests | pytest + httpx `ASGITransport` + in-memory storage fake |

## Project structure

```
app/
├── main.py                 # FastAPI instance: logging, metrics, middleware, handlers, routers
├── settings/               # config (pydantic-settings), logging_config, middleware
├── core/                   # decorators, exceptions (registry), metrics, observability,
│                           #   storage (S3 wrapper), dependencies (DbSession, auth, CallerNamespace)
├── db/                     # Base, async session, all_models (Alembic import list)
├── blobs/                  # (prompt 05-08) blob + blob_event models, upload, manage, temporary
├── namespaces/             # (prompt 04) namespace + per-namespace limits
├── admin/                  # (prompt 04) /admin/v1/* limit management
├── maintenance/            # (prompt 08) purge-expired
└── public/                 # (prompt 09) open /v1/public/* serving
```

Every domain is the standard five/six-file shape (`router`, `schemas`, `models`,
`service`, `repository`, `dependencies`) — see `anthropic-skills:fastapi-builder`.

## Step-by-step: run it locally

### 1. Prerequisites

- Docker + the shared `devbutter_shared` network and `infra/` stack
  (`shared-postgres` + `minio`).
- Poetry (for running tests / tooling outside Docker).

### 2. Configure environment

```bash
cp .env.example .env
# set SERVICE_API_KEY and ADMIN_API_KEY to real values
```

### 3. Bring up infra (shared-postgres + MinIO)

```bash
docker network create devbutter_shared 2>/dev/null || true
docker compose -f ../infra/docker-compose.yml up -d shared-postgres minio createbuckets
```

If the shared Postgres volume already exists, create the `blob` database once by
hand:

```bash
docker compose -f ../infra/docker-compose.yml exec shared-postgres \
  psql -U devbutter_admin -c "CREATE DATABASE blob;" \
  -c "CREATE USER blob WITH PASSWORD 'blob';" \
  -c "GRANT ALL PRIVILEGES ON DATABASE blob TO blob;"
```

### 4. Bring up the service

```bash
docker compose up --build
```

The entrypoint runs `alembic upgrade head` before Uvicorn. Open
<http://localhost:8003/docs>.

### 5. Run the automated tests

```bash
poetry install
poetry run pytest
poetry run ruff check .
poetry run mypy .
```

### 6. Run the curl smoke test

```bash
scripts/curl_smoke_test.sh        # (added in prompt 11)
```

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `staging` / `preprod` / `production` |
| `DATABASE_HOST` / `PORT` / `USER` / `PASSWORD` / `NAME` | `shared-postgres` / `5432` / `blob` | Pydantic monta `postgresql+asyncpg://` |
| `SERVICE_API_KEY` | — | `X-Service-Api-Key` for `/internal/v1/*` |
| `ALLOW_HEADER_NAMESPACE` | `true` | allows the deprecated shared-key + `X-Blob-Namespace` path; bearer `bbk_` keys always identify their namespace |
| `ADMIN_API_KEY` | — | `X-Admin-Api-Key` for `/admin/v1/*` |
| `SESSION_SECRET` | `dev-insecure-change-me` | signing secret for the admin dashboard cookie |
| `SESSION_COOKIE_NAME` | `butter_blob_admin` | admin dashboard cookie name |
| `AWS_REGION` | `us-east-1` | |
| `S3_BUCKET` | environment-selected | `devbutter-staging-blob` in preprod and `devbutter-prod-blob` in production; an explicit value overrides this. |
| `S3_ENDPOINT_URL` | `http://minio:9000` locally | unset outside development; MinIO endpoints are rejected there. |
| `S3_FORCE_PATH_STYLE` | `true` locally | automatically `false` outside development. |
| `S3_PRESIGN_EXPIRES_SECONDS` | `900` | ceiling for presigned URL lifetimes |
| `REDIS_URL` | — | Celery broker/result backend for async post-processing; empty disables the worker |
| `REDIS_QUEUE_NAME` | `blob-jobs` | Celery queue the worker consumes from |
| `CLAMAV_HOST` | — | enables ClamAV scanning when configured |
| `THUMBNAIL_WIDTHS` | `256` | comma-separated WebP thumbnail widths |
| `ENABLE_VIDEO_TRANSCODE` | `false` | reserves video jobs; ffmpeg wiring remains pending |
| `MAX_UPLOAD_BYTES` | `52428800` | global per-file ceiling |
| `DEFAULT_TEMPORARY_TTL_SECONDS` | `86400` | |
| `MAX_TEMPORARY_TTL_SECONDS` | `604800` | ttl cap; over ⇒ 422 |
| `PUBLIC_BASE_URL` | `http://localhost:8003` | base for `public_url` in responses |
| `AWS_EMF_*` | see `.env.example` | must keep `AWS_EMF_ENVIRONMENT=Local` |

## Admin dashboard

Open `/admin`. The session dashboard is independent from the machine-oriented
`/admin/v1/*` API, which continues to require `X-Admin-Api-Key`. It manages
namespace limits, blobs, and namespace-bound bearer keys. A new key is shown
once only and can later be revoked from the same namespace page.

Bootstrap the first active user after migrations:

```bash
poetry run python -c 'import asyncio; from app.adminui.repository import AdminUserRepository; from app.adminui.service import AdminUserService; from app.db.session import session_factory; exec("async def bootstrap():\\n async with session_factory() as db:\\n  await AdminUserService(AdminUserRepository(db)).register(\"admin@example.com\", \"change-me\")"); asyncio.run(bootstrap())'
```

## Deploying to AWS (shape, not IaC)

ECS Fargate service, image promoted by immutable digest. RDS `blob` database on
the shared cluster. A dedicated S3 bucket (SSE, public-access-block, lifecycle
rule expiring the `tmp/` prefix). Task role scoped to
`s3:{Get,Put,Delete}Object` / `s3:ListBucket` on that bucket. An EventBridge
schedule hitting `POST /internal/v1/maintenance/purge-expired`. See
`docs/terraform-notes.md` (added in prompt 11).

## Roadmap notes

Out of the phase-1 build, tracked as later prompts: per-namespace DB-backed bearer
keys (12), an async post-processing worker for virus scan / thumbnails /
transcode (13), a `devbutter_backend` client (14), and a CDN in front of the
public routes (15).
