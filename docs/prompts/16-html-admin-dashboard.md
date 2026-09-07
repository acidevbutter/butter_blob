# Prompt 16 — HTML admin dashboard

**Status:** ✅ done · **Runner:** Codex · **Phase:** 2.

## Goal
A minimal server-rendered admin UI over the same admin service, so limits and blob
inspection don't require curl.

## Depends on
04, 07.

## Reference
`../butter_relay/app/admin/*` + `../butter_relay/app/auth/*` — `SessionMiddleware`,
`admin_users` table (bcrypt), `request.session["admin_user_id"]`,
`SessionRequiredError` → 303 redirect, Jinja templating helper. `docs/spec.md` §4.

## Files
- `pyproject.toml` — add `jinja2`, `bcrypt`, `itsdangerous`, `python-multipart`
  (already present).
- `app/settings/config.py` — `session_secret: str = "dev-insecure-change-me"`,
  `session_cookie_name: str = "butter_blob_admin"`. `.env.example` updated.
- `app/settings/middleware.py` — add `SessionMiddleware` in `register_middleware`
  (after `RequestContextMiddleware`).
- `app/core/exceptions.py` — add `SessionRequiredError` (redirect to
  `/admin/login`) + handler (303), mirroring relay.
- `app/adminui/{__init__,router,templating,dependencies}.py` + `app/adminui/templates/`:
  - `auth`: `admin_users` model (`email` unique, `password_hash`, `is_active`),
    `AdminUserService` (bcrypt `register` / `verify`), `get_current_admin`
    dependency (session → user, else `SessionRequiredError`).
  - pages (all `GET` HTML unless noted):
    - `GET /admin/login`, `POST /admin/login` (form), `POST /admin/logout`
    - `GET /admin` — namespace list + usage bars
    - `GET /admin/namespaces/{slug}` — limits form; `POST` writes via
      `NamespaceService.set_limits` (the same path as `PUT /admin/v1/.../limits`)
    - `GET /admin/namespaces/{slug}/blobs` — filterable blob table (reuses
      `BlobRepository.list` without the owner restriction — admin sees all);
      row → `GET /admin/blobs/{id}` detail (metadata + `blob_events` timeline);
      `POST /admin/blobs/{id}/delete` (soft).
  - `templating.py` — `Jinja2Templates` + a `render(request, name, **ctx)` helper;
    base layout, minimal CSS inline.
- `app/main.py` — `include_router(adminui_router)`. Keep `GET /` redirecting to
  `/docs` (or change to `/admin` — decide and note).
- `app/db/all_models.py` — add `admin_users`. Migration.
- `README.md` / `docs/spec.md` — document the dashboard + first-admin bootstrap
  (`python -c "..."` calling `AdminUserService.register`, like relay's smoke test).

## Acceptance
`tests/test_adminui.py`:
- `GET /admin` without a session ⇒ 303 → `/admin/login`
- register an admin (service layer), `POST /admin/login` ⇒ 303 + cookie;
  authed `GET /admin` ⇒ 200 lists namespaces
- submit the limits form → values readable via `GET /admin/v1/namespaces/{slug}`
  (JSON) — proves both paths share the service
- blob table filters; blob detail shows events; soft-delete from the UI flips
  `status`
- the JSON `/admin/v1/*` routes still work unchanged with `X-Admin-Api-Key`
- `ruff` / `mypy` / `pytest` green

## Notes
The `X-Admin-Api-Key` JSON API and the session dashboard coexist — machine
callers keep using the header; humans use the cookie. Don't gate the JSON routes
behind the session.

## Completion

`GET /` remains redirected to `/docs`. The dashboard is available at `/admin`;
its bootstrap command and session settings are documented in `README.md`.
