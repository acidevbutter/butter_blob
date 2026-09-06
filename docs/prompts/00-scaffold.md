# Prompt 00 — Project scaffold & tooling

**Status:** ✅ done.

## Goal
A Poetry project that boots to `/health` and `/docs`, with Docker + compose wired
to the shared infra, matching the `../butter_relay` skeleton.

## Depends on
Nothing.

## Reference
`../butter_relay/pyproject.toml`, `../butter_relay/.gitignore`,
`../asaas_payment/Dockerfile`, `../asaas_payment/docker-entrypoint.sh`,
`../butter_relay/docker-compose.yml`, `../butter_relay/README.md`.

## Files
- `pyproject.toml` — Poetry, Python `^3.12`. Deps: fastapi, uvicorn[standard],
  pydantic[email], pydantic-settings, sqlalchemy, greenlet, alembic, asyncpg,
  psycopg2-binary, boto3, httpx, python-multipart, python-slugify, pillow,
  aws-embedded-metrics. Dev: pytest, pytest-asyncio, ruff, mypy, aiosqlite,
  moto[s3]. `ruff` line-length 100 / `select E,F,I,UP,B,SIM` / isort
  `known-third-party = ["alembic"]`. `mypy` strict, `python_version 3.12`,
  overrides: `tests.*` relaxes untyped-def rules, `boto3.*/botocore.*/moto.*`
  `ignore_missing_imports`. `pytest` `asyncio_mode = auto`.
- `Dockerfile` — `python:3.12-slim`, `POETRY_VIRTUALENVS_CREATE=false`,
  `poetry install --only main --no-root`, non-root `appuser` (uid 1000),
  `ENTRYPOINT ["docker-entrypoint.sh"]`, `CMD` uvicorn on `:8000`.
- `docker-entrypoint.sh` — `set -eu; alembic upgrade head; exec "$@"`. Executable.
- `docker-compose.yml` — `api` service: `build .`, `uvicorn ... --reload`,
  `8003:8000`, `env_file .env`, env overrides (`DATABASE_URL`, `S3_ENDPOINT_URL`,
  `S3_FORCE_PATH_STYLE`, dummy `AWS_*`), volumes `./app` + `./alembic`,
  `develop.watch`, networks `default` + external `devbutter_shared` alias
  `blob-api`.
- `.env.example` — every setting + `AWS_ACCESS_KEY_ID/SECRET` + `AWS_EMF_*`.
- `.gitignore` — relay's.
- `app/__init__.py`, `app/settings/__init__.py`, `app/core/__init__.py`,
  `app/db/__init__.py`, `tests/__init__.py`.
- `app/main.py` — minimal `FastAPI(title="Butter Blob")` + `GET /health`.
- `README.md` — heading tree mirrored from `../butter_relay/README.md`.

## Steps
1. Write the files above.
2. `git branch -m main master`.
3. `poetry lock && poetry install`.
4. `poetry run uvicorn app.main:app` boots; `curl localhost:8000/health` → `{"status":"ok"}`.

## Acceptance
- `poetry run ruff check .` clean.
- `poetry run pytest` exits 0 (no tests yet or the health test from prompt 01).
- `cp .env.example .env && docker compose config` valid (then remove the temp `.env`).
- `git rev-parse --abbrev-ref HEAD` → `master`.

## Notes
Python 3.12 (not 3.11 like relay/asaas) — matches `butter_mind`.
