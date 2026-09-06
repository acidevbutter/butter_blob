# Prompt 10 — Infra wiring (`infra/` repo)

**Status:** ⬜ not started.

## Goal
Make the shared dev stack able to run butter_blob: a `blob` database on
`shared-postgres` and a `minio` service with the bucket pre-created.

## Depends on
Nothing in butter_blob (can run any time), but only useful once 00–09 exist.

## Reference
`../infra/docker-compose.yml`, `../infra/postgres/init/001-create-databases.sh`,
`../infra/.env.example`, `../butter_relay/docker-compose.yml` (network alias
pattern), `docs/spec.md` §11.

## Files (all under `../infra/`)
- `postgres/init/001-create-databases.sh` — add a line alongside the others:
  `create_database "$BLOB_DB_NAME" "$BLOB_DB_USER" "$BLOB_DB_PASSWORD"`.
- `.env` and `.env.example` — add:
  ```
  BLOB_DB_NAME=blob
  BLOB_DB_USER=blob
  BLOB_DB_PASSWORD=blob
  MINIO_ROOT_USER=minioadmin
  MINIO_ROOT_PASSWORD=minioadmin
  BLOB_S3_BUCKET=devbutter-blob-local
  ```
- `docker-compose.yml`:
  - add `shared-postgres` `environment:` entries `BLOB_DB_NAME` / `BLOB_DB_USER` /
    `BLOB_DB_PASSWORD` (so the init script sees them).
  - new service `minio`:
    ```yaml
    minio:
      image: minio/minio:RELEASE.2024-09-13T20-26-02Z
      command: server /data --console-address ":9001"
      environment:
        MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
        MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
      ports: ["9000:9000", "9001:9001"]
      volumes: ["minio_data:/data"]
      healthcheck:
        test: ["CMD", "mc", "ready", "local"]
        interval: 5s
        timeout: 3s
        retries: 20
      networks:
        default:
        devbutter_shared:
          aliases: ["minio"]
    ```
  - new one-shot service `createbuckets`:
    ```yaml
    createbuckets:
      image: minio/mc:RELEASE.2024-09-16T17-43-14Z
      depends_on: { minio: { condition: service_healthy } }
      entrypoint: >
        /bin/sh -c "
        mc alias set local http://minio:9000 $${MINIO_ROOT_USER:-minioadmin} $${MINIO_ROOT_PASSWORD:-minioadmin} &&
        mc mb --ignore-existing local/$${BLOB_S3_BUCKET:-devbutter-blob-local} &&
        mc anonymous set none local/$${BLOB_S3_BUCKET:-devbutter-blob-local}
        "
      environment:
        MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
        MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
        BLOB_S3_BUCKET: ${BLOB_S3_BUCKET:-devbutter-blob-local}
      networks: [default]
    ```
  - top-level `volumes:` — add `minio_data:`.
- `README.md` / `CHANGELOG.md` — note the new `blob` DB and the MinIO service +
  console at `http://localhost:9001`.

## Steps / manual
The init script only runs on a **fresh** Postgres volume. On an existing dev
volume, create the DB/role once:
```bash
docker compose -f infra/docker-compose.yml exec shared-postgres \
  psql -U "$POSTGRES_ADMIN_USER" -v ON_ERROR_STOP=1 <<'SQL'
CREATE DATABASE blob;
CREATE USER blob WITH PASSWORD 'blob';
GRANT ALL PRIVILEGES ON DATABASE blob TO blob;
SQL
```

## Acceptance
- `docker compose -f infra/docker-compose.yml config` valid.
- `docker network create devbutter_shared 2>/dev/null || true` then
  `docker compose -f infra/docker-compose.yml up -d shared-postgres minio createbuckets`
  → `createbuckets` exits 0, bucket exists (`mc ls local`).
- From `butter_blob/`: `cp .env.example .env` + `docker compose up --build` boots;
  `curl localhost:8003/health/ready` → 200 (DB + S3 both reachable).

## Notes
Pin the `minio` / `mc` image tags to the same release. `mc anonymous set none`
keeps the bucket private (butter_blob always serves via presigned URLs).
