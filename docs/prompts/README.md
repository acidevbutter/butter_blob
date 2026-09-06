# Implementation prompts

Build `butter_blob` one file at a time. Each `NN-*.md` is self-contained:
*Goal / Depends on / Reference / Files / Steps / Acceptance / Notes*.

Rules:
- Do a prompt only when its **Depends on** is merged.
- [`../spec.md`](../spec.md) is authoritative — update it in the same slice if you
  change behaviour.
- Tick [`../TODO.md`](../TODO.md) when a prompt's deliverables + acceptance pass.

| # | Prompt | Status | Runner |
|---|---|---|---|
| 00 | [scaffold](00-scaffold.md) | ✅ done | — |
| 01 | [settings-core](01-settings-core.md) | ✅ done | — |
| 02 | [db-alembic](02-db-alembic.md) | ✅ done | — |
| 03 | [storage](03-storage.md) | ✅ done | — |
| 04 | [namespaces-admin](04-namespaces-admin.md) | ⬜ | — |
| 05 | [blobs-datalayer](05-blobs-datalayer.md) | ⬜ | — |
| 06 | [blobs-upload](06-blobs-upload.md) | ⬜ | — |
| 07 | [blobs-manage](07-blobs-manage.md) | ⬜ | — |
| 08 | [temporary-purge](08-temporary-purge.md) | ⬜ | — |
| 09 | [public-routes](09-public-routes.md) | ⬜ | — |
| 10 | [infra](10-infra.md) | ⬜ | — |
| 11 | [docs-smoke](11-docs-smoke.md) | ⬜ | — |
| 12 | [namespace-api-keys](12-namespace-api-keys.md) | ⬜ | Codex (phase 2) |
| 13 | [postprocessing-worker](13-postprocessing-worker.md) | ⬜ | Codex (phase 2) |
| 14 | [devbutter-backend-client](14-devbutter-backend-client.md) | ⬜ | Codex (phase 2) |
| 15 | [public-cdn](15-public-cdn.md) | ⬜ | Codex (phase 2) |
| 16 | [html-admin-dashboard](16-html-admin-dashboard.md) | ⬜ | Codex (phase 2) |

Phase 1 (00–11) is the working service. Phase 2 (12–16) is the previously
"out of scope" work, written to be run by Codex.
