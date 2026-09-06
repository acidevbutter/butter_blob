"""Imported by alembic/env.py (and tests/conftest.py) so Base.metadata sees every
table before autogenerate / create_all.

Adding a new domain's `models` module here is required -- a domain added without
updating this import list is silently invisible to
`alembic revision --autogenerate` and to `Base.metadata.create_all` in tests.

No domain models exist yet; each domain prompt (04+) adds its line here, e.g.

    from app.namespaces import models as namespaces_models  # noqa: F401
    from app.blobs import models as blobs_models  # noqa: F401
"""
