# Prompt 02 — Async DB layer & Alembic

**Status:** ✅ done.

## Goal
Async SQLAlchemy 2.0 engine/session, the Alembic tree (async `env.py`, timestamp
filenames), and the pytest fixtures every later test uses.

## Depends on
01.

## Reference
`../butter_relay/app/db/*`, `../butter_relay/alembic.ini`,
`../butter_relay/alembic/env.py`, `../butter_relay/alembic/script.py.mako`,
`../butter_relay/tests/conftest.py`.

## Files
- `app/db/base.py` — `class Base(DeclarativeBase): pass`.
- `app/db/session.py` — `engine = create_async_engine(settings.database_url,
  pool_pre_ping=True)`; `session_factory = async_sessionmaker(engine,
  expire_on_commit=False)`; `async def get_db_session() -> AsyncGenerator[...]`.
- `app/db/all_models.py` — docstring only for now; each domain prompt adds its
  `from app.<domain> import models as ...  # noqa: F401` line.
- `alembic.ini` — relay's, incl. `file_template =
  %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s`,
  blank `sqlalchemy.url`.
- `alembic/env.py` — async: `from alembic import context`; `from app.db import
  all_models`; `config.set_main_option("sqlalchemy.url", settings.database_url)`;
  `target_metadata = Base.metadata`; `async_engine_from_config` + `NullPool` +
  `asyncio.run(run_migrations_online())`. Import order must satisfy ruff isort
  (`alembic` is third-party via `known-third-party`).
- `alembic/script.py.mako` — modern typed (`from collections.abc import Sequence`,
  `down_revision: str | None`, ...).
- `alembic/versions/.gitkeep`.
- `tests/conftest.py`:
  - `TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"`, `TEST_SERVICE_API_KEY`,
    `TEST_ADMIN_API_KEY`, `TEST_NAMESPACE`.
  - `_settings_override` (autouse) — set `settings.service_api_key` /
    `settings.admin_api_key` to the test values, restore after.
  - `db_session` — fresh engine, `Base.metadata.create_all`, yields one session.
  - `blob_storage` — installs `InMemoryBlobStorage` via
    `app.dependency_overrides[get_blob_storage]`, yields it (prompt 03 adds the
    fake; until then this fixture may be a stub).
  - `client` — depends on `db_session` + `blob_storage`; overrides
    `get_db_session`; `AsyncClient(transport=ASGITransport(app))`.
  - `internal_headers` — `{X-Service-Api-Key, X-Blob-Namespace}`.
  - `admin_headers` — `{X-Admin-Api-Key}`.
  - Import `get_db_session` from `app.db.session` (not re-exported via
    `app.core.dependencies`, which `mypy --strict` rejects).

## Acceptance
- `DATABASE_URL=sqlite+aiosqlite:///./_probe.db poetry run alembic upgrade head`
  runs clean (creates `alembic_version`); `alembic current` works. Remove the file.
- `poetry run pytest` still green; `mypy` / `ruff` clean.

## Notes
No domain tables yet. `Base.metadata.create_all` in tests only sees models that
`app/db/all_models.py` imports — every domain prompt MUST add its line there.
