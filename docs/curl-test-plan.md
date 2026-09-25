# butter_blob — Route Map & curl Test Plan

Every route in the service, grouped the way [`CLAUDE.md`](../CLAUDE.md) groups them
(meta → public → internal → admin → admin UI), with a runnable `curl` case per
endpoint. Written to be executed **against production** endpoint by endpoint, so
read the safety notes before running anything that isn't a plain `GET`.

Routes were read directly from the routers, so this reflects code as of the
current branch: [`app/main.py`](../app/main.py), [`app/public/router.py`](../app/public/router.py),
[`app/namespaces/router.py`](../app/namespaces/router.py), [`app/blobs/router.py`](../app/blobs/router.py),
[`app/maintenance/router.py`](../app/maintenance/router.py), [`app/admin/router.py`](../app/admin/router.py),
[`app/api_keys/router.py`](../app/api_keys/router.py), [`app/adminui/router.py`](../app/adminui/router.py).
If code and this doc disagree later, re-derive from the routers — per `CLAUDE.md`,
[`docs/spec.md`](spec.md) (not this file) is the authoritative contract.

## ⚠️ Safety notes — read first

- **Use a dedicated namespace for every mutating test**, never a real app's
  namespace. This plan uses `qa-smoke` throughout; create it first (§4.1) and
  don't touch any other slug with `POST` / `PATCH` / `PUT` / `DELETE`.
- **`DELETE /internal/v1/blobs/{blob_id}`** — only run against a `blob_id` you
  created earlier in the same run. `hard=true` bypasses the soft-delete and is
  unrecoverable.
- **`POST /internal/v1/maintenance/purge-expired`** — always pass
  `?namespace=qa-smoke`. Omitting `namespace` purges expired blobs across
  *every* namespace in prod.
- **`POST /admin/v1/namespaces/{slug}/keys/{key_id}/revoke`** — irreversible.
  Only revoke keys created in §4.2 of this same run.
- Treat every `SERVICE_API_KEY`, `ADMIN_API_KEY`, and `bbk_...` plaintext key
  printed by these commands as a secret — don't paste output into shared
  channels or commits.
- 404 in the internal/admin trees can mean either "wrong/missing key" or
  "resource doesn't exist" — that's intentional fail-closed behavior
  (`app/core/dependencies.py`), not a bug to chase.

## 0. Setup

```bash
export BASE_URL="https://blob.devbutter.tech"
export SERVICE_API_KEY="<prod SERVICE_API_KEY>"
export ADMIN_API_KEY="<prod ADMIN_API_KEY>"
export NAMESPACE="qa-smoke"

echo "smoke test $(date -u +%FT%TZ)" > /tmp/blob-smoke.txt
```

All examples assume `jq` is installed for parsing JSON responses; swap in
whatever's available if not.

---

## 1. Meta routes (no auth)

#### `GET /health`
Liveness only — no DB/S3 check.
```bash
curl -sS -i "$BASE_URL/health"
```
Expect: `200 {"status":"ok"}`

#### `GET /health/ready`
Readiness — checks DB (`SELECT 1`) and S3 bucket existence.
```bash
curl -sS -i "$BASE_URL/health/ready"
```
Expect: `200 {"status":"ok"}`, or `503` with `{"detail":"database unavailable"}` /
`{"detail":"object storage unavailable"}` if a dependency is down.

#### `GET /`
Redirects to Swagger UI.
```bash
curl -sS -i "$BASE_URL/"
```
Expect: `307` (or `200` if you add `-L`) → `Location: /docs`

---

## 2. Public routes — `/v1/public/*` (no auth)

Serves only blobs with `visibility=public`. You need a real `{namespace}` /
`{public_slug}` pair — get one from a blob you created in §3.2 with
`visibility=public`.

```bash
export PUBLIC_SLUG="<public_slug from a blob you created below>"
```

#### `GET /v1/public/{namespace}/{public_slug}/meta`
```bash
curl -sS -i "$BASE_URL/v1/public/$NAMESPACE/$PUBLIC_SLUG/meta"
```
Expect: `200` with `filename`, `content_type`, `byte_size`, `created_at`,
`expires_at`, and a `Cache-Control` header.

Error case — unknown slug:
```bash
curl -sS -i "$BASE_URL/v1/public/$NAMESPACE/does-not-exist/meta"
```
Expect: `404`

#### `GET /v1/public/{namespace}/{public_slug}`
302-redirects to a presigned S3 URL (temporary blobs) or the CDN URL
(permanent, when `PUBLIC_CDN_BASE_URL` is set).
```bash
curl -sS -i "$BASE_URL/v1/public/$NAMESPACE/$PUBLIC_SLUG"
curl -sS -i "$BASE_URL/v1/public/$NAMESPACE/$PUBLIC_SLUG?disposition=attachment"
```
Expect: `302` with `Location` + `Cache-Control` headers. Add `-L` to follow and
actually download the bytes.

Error case — blob visibility is `private` or blob doesn't exist:
```bash
curl -sS -i "$BASE_URL/v1/public/$NAMESPACE/some-private-slug"
```
Expect: `404`

---

## 3. Internal routes — `/internal/v1/*`

Auth: **either**
`X-Service-Api-Key: $SERVICE_API_KEY` + `X-Blob-Namespace: $NAMESPACE`
**or** `Authorization: Bearer <bbk_...>` (a namespace-scoped key from §4.2 —
preferred going forward per `docs/spec.md`). Examples below use the shared
service key; swap the header for a `bbk_...` key to test that path too.

Auth error case (shared for every route in this section) — bad/missing key:
```bash
curl -sS -i "$BASE_URL/internal/v1/namespaces/$NAMESPACE" \
  -H "X-Service-Api-Key: wrong" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `404` (fails closed, not `401` — the internal surface is invisible
without the shared secret)

### 3.1 Namespaces

#### `GET /internal/v1/namespaces/{slug}`
First call auto-upserts `$NAMESPACE` if it doesn't exist yet.
```bash
curl -sS -i "$BASE_URL/internal/v1/namespaces/$NAMESPACE" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with usage fields (`blob_count`, `total_bytes`, `temporary_count`)

Error case — another namespace's slug (cross-namespace read):
```bash
curl -sS -i "$BASE_URL/internal/v1/namespaces/some-other-namespace" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `404`

#### `PATCH /internal/v1/namespaces/{slug}`
Self-service update of `name`/`description` only (limits are admin-only).
```bash
curl -sS -i -X PATCH "$BASE_URL/internal/v1/namespaces/$NAMESPACE" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -H "Content-Type: application/json" \
  -d '{"name":"QA Smoke","description":"curl test plan namespace"}'
```
Expect: `200` with the updated `NamespaceRead`

### 3.2 Blobs

#### `POST /internal/v1/blobs` — direct multipart upload
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/blobs" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -F "file=@/tmp/blob-smoke.txt;type=text/plain" \
  -F "visibility=public" \
  -F "metadata={\"source\":\"curl-test-plan\"}"
```
Expect: `201` with a `BlobRead`; capture `id` and (if `visibility=public`)
`public_slug` / `public_url`:
```bash
export BLOB_ID=$(curl -sS -X POST "$BASE_URL/internal/v1/blobs" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -F "file=@/tmp/blob-smoke.txt;type=text/plain" -F "visibility=public" \
  | tee /tmp/blob-created.json | jq -r .id)
export PUBLIC_SLUG=$(jq -r .public_slug /tmp/blob-created.json)
```

Error case — disallowed format for the namespace (set `allowed_extensions` on
`qa-smoke` first via §4.1 to actually trigger this):
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/blobs" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -F "file=@/tmp/blob-smoke.txt;type=text/plain"
```
Expect: `415` once the namespace's `allowed_extensions`/`allowed_content_types`
excludes `.txt`/`text/plain`; otherwise `201`.

#### `POST /internal/v1/blobs/presign` — client-direct upload flow
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/blobs/presign" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -H "Content-Type: application/json" \
  -d '{"filename":"smoke.txt","content_type":"text/plain","visibility":"private"}'
```
Expect: `201` with `blob_id`, `upload_url`, `method:"PUT"`, `headers`,
`expires_at`. Then actually upload and complete:
```bash
export PRESIGN=$(curl -sS -X POST "$BASE_URL/internal/v1/blobs/presign" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -H "Content-Type: application/json" \
  -d '{"filename":"smoke.txt","content_type":"text/plain"}')
export UPLOAD_URL=$(echo "$PRESIGN" | jq -r .upload_url)
export PRESIGN_BLOB_ID=$(echo "$PRESIGN" | jq -r .blob_id)

curl -sS -i -X PUT "$UPLOAD_URL" -H "Content-Type: text/plain" \
  --data-binary @/tmp/blob-smoke.txt
```

#### `POST /internal/v1/blobs/{blob_id}/complete`
Marks a presigned upload as done (must be called after the `PUT` above).
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/blobs/$PRESIGN_BLOB_ID/complete" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with `status:"stored"` (or `"processing"` if async post-processing
is enabled for this content type)

Error case — completing a blob id that was never presigned / already
completed / belongs to another namespace:
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/blobs/00000000-0000-0000-0000-000000000000/complete" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `404`

#### `GET /internal/v1/blobs` — list with filters
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs?limit=10" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"

curl -sS -i "$BASE_URL/internal/v1/blobs?visibility=public&status=stored&temporary=false&limit=50" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with a JSON array (only `$NAMESPACE`'s blobs, never another
namespace's)

Error case — `limit` out of range (`> 500`):
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs?limit=9999" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `422`

#### `GET /internal/v1/blobs/{blob_id}`
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs/$BLOB_ID" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with the full `BlobRead`

Error case — expired temporary blob:
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs/<an-expired-blob-id>" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `410`

#### `GET /internal/v1/blobs/{blob_id}/download-url`
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs/$BLOB_ID/download-url?disposition=attachment" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with `{"url": "...", "expires_at": "..."}`. Then:
```bash
curl -sS -i "$(curl -sS "$BASE_URL/internal/v1/blobs/$BLOB_ID/download-url" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" | jq -r .url)"
```

#### `GET /internal/v1/blobs/{blob_id}/events`
```bash
curl -sS -i "$BASE_URL/internal/v1/blobs/$BLOB_ID/events" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with an array of `{action, detail, at}` (at least `created`,
`uploaded`)

#### `PATCH /internal/v1/blobs/{blob_id}`
```bash
curl -sS -i -X PATCH "$BASE_URL/internal/v1/blobs/$BLOB_ID" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE" \
  -H "Content-Type: application/json" \
  -d '{"metadata":{"source":"curl-test-plan","patched":true}}'
```
Expect: `200` with the updated `BlobRead`

#### `DELETE /internal/v1/blobs/{blob_id}`
Soft delete by default; only pass `hard=true` if you mean it.
```bash
curl -sS -i -X DELETE "$BASE_URL/internal/v1/blobs/$BLOB_ID" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `204`

Error case — deleting the same id twice:
```bash
curl -sS -i -X DELETE "$BASE_URL/internal/v1/blobs/$BLOB_ID" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `404`

### 3.3 Maintenance

#### `POST /internal/v1/maintenance/purge-expired`
**Always scope with `namespace=` in prod** (see safety notes).
```bash
curl -sS -i -X POST "$BASE_URL/internal/v1/maintenance/purge-expired?namespace=$NAMESPACE" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NAMESPACE"
```
Expect: `200` with `{"scanned": N, "purged": N, "bytes_reclaimed": N}`

---

## 4. Admin routes — `/admin/v1/*`

Auth: `X-Admin-Api-Key: $ADMIN_API_KEY`.

Auth error case (shared for every route in this section):
```bash
curl -sS -i "$BASE_URL/admin/v1/namespaces" -H "X-Admin-Api-Key: wrong"
```
Expect: `404`

### 4.1 Namespaces

#### `POST /admin/v1/namespaces` — create `qa-smoke` up front
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"slug":"qa-smoke","name":"QA Smoke Tests","allowed_extensions":[".txt",".png"],"max_file_bytes":5242880}'
```
Expect: `201` with the created `NamespaceRead`

Error case — duplicate slug:
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"slug":"qa-smoke","name":"dup"}'
```
Expect: `409`

Error case — unknown field (`extra="forbid"`):
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"slug":"qa-smoke-2","typo_field":true}'
```
Expect: `422`

#### `GET /admin/v1/namespaces` — list all, with usage
```bash
curl -sS -i "$BASE_URL/admin/v1/namespaces" -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `200` with every namespace + usage

#### `GET /admin/v1/namespaces/{slug}`
```bash
curl -sS -i "$BASE_URL/admin/v1/namespaces/$NAMESPACE" -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `200`

Error case — unknown slug:
```bash
curl -sS -i "$BASE_URL/admin/v1/namespaces/does-not-exist" -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `404`

#### `PUT /admin/v1/namespaces/{slug}/limits`
```bash
curl -sS -i -X PUT "$BASE_URL/admin/v1/namespaces/$NAMESPACE/limits" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"max_storage_bytes":104857600,"max_file_bytes":5242880,"allowed_content_types":["text/plain","image/png"],"allowed_extensions":[".txt",".png"],"image_compression_quality":80,"image_max_dimension":2048}'
```
Expect: `200` with the updated `NamespaceRead`

Error case — out-of-range compression quality:
```bash
curl -sS -i -X PUT "$BASE_URL/admin/v1/namespaces/$NAMESPACE/limits" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"image_compression_quality":150}'
```
Expect: `422`

### 4.2 API keys — `/admin/v1/namespaces/{slug}/keys`

#### `POST /admin/v1/namespaces/{slug}/keys`
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces/$NAMESPACE/keys" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"label":"curl-test-plan"}'
```
Expect: `201` with `plaintext_key` (`bbk_...`) — **shown only this once**,
save it to test the `Authorization: Bearer` path in §3:
```bash
export API_KEY_JSON=$(curl -sS -X POST "$BASE_URL/admin/v1/namespaces/$NAMESPACE/keys" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"label":"curl-test-plan"}')
export BBK_KEY=$(echo "$API_KEY_JSON" | jq -r .plaintext_key)
export KEY_ID=$(echo "$API_KEY_JSON" | jq -r .id)

curl -sS -i "$BASE_URL/internal/v1/namespaces/$NAMESPACE" -H "Authorization: Bearer $BBK_KEY"
```

#### `GET /admin/v1/namespaces/{slug}/keys`
```bash
curl -sS -i "$BASE_URL/admin/v1/namespaces/$NAMESPACE/keys" -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `200` with an array of `ApiKeyRead` (no `plaintext_key` field — hashes
are never re-exposed)

#### `POST /admin/v1/namespaces/{slug}/keys/{key_id}/revoke`
Irreversible — see safety notes.
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces/$NAMESPACE/keys/$KEY_ID/revoke" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `200` with `revoked_at` set

Error case — revoking a key that belongs to a different namespace, or an
already-revoked key id under the wrong slug:
```bash
curl -sS -i -X POST "$BASE_URL/admin/v1/namespaces/some-other-namespace/keys/$KEY_ID/revoke" \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
Expect: `404`

---

## 5. Admin UI — `/admin/*` (HTML, session cookie)

Server-rendered dashboard, not a JSON API — lower priority for an
endpoint-by-endpoint prod smoke test, but mapped for completeness. Auth is a
signed session cookie (`SESSION_COOKIE_NAME`, default `butter_blob_admin`) set
by `POST /admin/login`; there's no seed-admin-user route in this router, so
you need an existing admin user's email/password.

```bash
export ADMIN_EMAIL="<admin user email>"
export ADMIN_PASSWORD="<admin user password>"
export COOKIES=/tmp/blob-admin-cookies.txt
```

#### `GET /admin/login`
```bash
curl -sS -i "$BASE_URL/admin/login"
```
Expect: `200` (login form)

#### `POST /admin/login`
```bash
curl -sS -i -c "$COOKIES" -X POST "$BASE_URL/admin/login" \
  --data-urlencode "email=$ADMIN_EMAIL" --data-urlencode "password=$ADMIN_PASSWORD"
```
Expect: `303 → /admin` with `Set-Cookie`; wrong credentials re-render the form
with `200` and an error message (not a redirect)

#### `GET /admin` — dashboard
```bash
curl -sS -i -b "$COOKIES" "$BASE_URL/admin"
```
Expect: `200` HTML listing namespaces; `303 → /admin/login` if the cookie is
missing/expired

#### `GET /admin/namespaces/{slug}`
```bash
curl -sS -i -b "$COOKIES" "$BASE_URL/admin/namespaces/$NAMESPACE"
```
Expect: `200` HTML with namespace detail + its API keys

#### `POST /admin/namespaces/{slug}` — update limits via form
```bash
curl -sS -i -b "$COOKIES" -X POST "$BASE_URL/admin/namespaces/$NAMESPACE" \
  --data-urlencode "max_file_bytes=5242880" --data-urlencode "max_storage_bytes=104857600" \
  --data-urlencode "allowed_content_types=text/plain,image/png" \
  --data-urlencode "allowed_extensions=.txt,.png" \
  --data-urlencode "image_compression_quality=80" --data-urlencode "image_max_dimension=2048"
```
Expect: `303 → /admin/namespaces/qa-smoke`

#### `POST /admin/namespaces/{slug}/keys` — create key via form
```bash
curl -sS -i -b "$COOKIES" -X POST "$BASE_URL/admin/namespaces/$NAMESPACE/keys" \
  --data-urlencode "label=admin-ui-smoke"
```
Expect: `200` HTML with the plaintext key shown once, `Cache-Control: no-store`

#### `POST /admin/namespaces/{slug}/keys/{key_id}/revoke`
```bash
curl -sS -i -b "$COOKIES" -X POST "$BASE_URL/admin/namespaces/$NAMESPACE/keys/$KEY_ID/revoke"
```
Expect: `303 → /admin/namespaces/qa-smoke`

#### `GET /admin/namespaces/{slug}/blobs`
```bash
curl -sS -i -b "$COOKIES" "$BASE_URL/admin/namespaces/$NAMESPACE/blobs"
curl -sS -i -b "$COOKIES" "$BASE_URL/admin/namespaces/$NAMESPACE/blobs?visibility=public&status=stored"
```
Expect: `200` HTML table of blobs

#### `GET /admin/blobs/{blob_id}`
```bash
curl -sS -i -b "$COOKIES" "$BASE_URL/admin/blobs/$BLOB_ID"
```
Expect: `200` HTML with blob detail + events; `404` if the id doesn't exist

#### `POST /admin/blobs/{blob_id}/delete`
Soft-deletes (`hard=false`) — irreversible in the UI (no undo control).
```bash
curl -sS -i -b "$COOKIES" -X POST "$BASE_URL/admin/blobs/$BLOB_ID/delete"
```
Expect: `303 → /admin/namespaces/{blob's namespace}/blobs`

#### `POST /admin/logout`
```bash
curl -sS -i -b "$COOKIES" -c "$COOKIES" -X POST "$BASE_URL/admin/logout"
```
Expect: `303 → /admin/login`, session cookie cleared

---

## Route count

| Tree | Routes |
|---|---|
| Meta | 3 (`/health`, `/health/ready`, `/`) |
| Public (`/v1/public/*`) | 2 |
| Internal (`/internal/v1/*`) | 12 (9 blobs + 2 namespaces + 1 maintenance) |
| Admin API (`/admin/v1/*`) | 7 (4 namespaces + 3 api-keys) |
| Admin UI (`/admin/*`, HTML) | 11 |
| **Total** | **35** |
