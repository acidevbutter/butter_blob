#!/bin/bash
# Daily route-health smoke test against preprod. Mirrors docs/curl-test-plan.md,
# scoped to a single dedicated namespace so it never touches real app data.
#
# Credentials: reads BASE_URL / SERVICE_API_KEY / ADMIN_API_KEY from .env.preprod
# (gitignored, see .env.preprod.example) or from the environment if already set.
#
# Writes tab-separated results (name, actual, expected, status) to stdout and to
# $RESULTS_FILE. Exits non-zero if any check's actual status doesn't match expected.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env.preprod" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env.preprod"
  set +a
fi

: "${BASE_URL:?BASE_URL not set (put it in .env.preprod or export it)}"
: "${SERVICE_API_KEY:?SERVICE_API_KEY not set (put it in .env.preprod or export it)}"
: "${ADMIN_API_KEY:?ADMIN_API_KEY not set (put it in .env.preprod or export it)}"

NS="qa-smoke-daily"
RESULTS_FILE="${RESULTS_FILE:-/tmp/blob_preprod_results.tsv}"
FAIL_COUNT=0
: > "$RESULTS_FILE"

log() {
  local name="$1" expected="$2" actual="$3"
  local status="FAIL"
  if [[ "$expected" == *"$actual"* ]]; then status="PASS"; else FAIL_COUNT=$((FAIL_COUNT + 1)); fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$actual" "$expected" "$status" | tee -a "$RESULTS_FILE"
}

code() { curl -sS -o /dev/null -w '%{http_code}' "$@"; }

# Single request returning body and status: sets RESP_BODY and RESP_CODE.
# Avoids issuing the same POST twice, which would orphan a blob per run.
request() {
  local out
  out=$(curl -sS -w '\n%{http_code}' "$@")
  RESP_CODE="${out##*$'\n'}"
  RESP_BODY="${out%$'\n'*}"
}

TMP_FILE=$(mktemp)
echo "preprod smoke $(date -u +%FT%TZ)" > "$TMP_FILE"
trap 'rm -f "$TMP_FILE"' EXIT

# 1. Meta
log "GET /health" "200" "$(code "$BASE_URL/health")"
log "GET /health/ready" "200" "$(code "$BASE_URL/health/ready")"
log "GET /" "307|200" "$(code "$BASE_URL/")"

# Ensure the smoke namespace exists (idempotent: 201 first run, 409 after)
NS_JSON="{\"slug\":\"$NS\",\"name\":\"QA Smoke (daily)\",\"allowed_extensions\":[\".txt\",\".png\"],\"max_file_bytes\":5242880}"
log "POST /admin/v1/namespaces (ensure qa-smoke-daily)" "409|201" "$(code -X POST "$BASE_URL/admin/v1/namespaces" -H "X-Admin-Api-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" -d "$NS_JSON")"

# 3.1 Namespaces
log "GET /internal/v1/namespaces/{slug}" "200" "$(code "$BASE_URL/internal/v1/namespaces/$NS" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"
log "AUTH bad service key" "404" "$(code "$BASE_URL/internal/v1/namespaces/$NS" -H "X-Service-Api-Key: wrong" -H "X-Blob-Namespace: $NS")"

# 3.2 Blobs — direct upload
request -X POST "$BASE_URL/internal/v1/blobs" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS" \
  -F "file=@$TMP_FILE;type=text/plain" -F "visibility=public"
log "POST /internal/v1/blobs (direct upload)" "201" "$RESP_CODE"
BLOB_ID=$(echo "$RESP_BODY" | jq -r .id 2>/dev/null)

log "GET /internal/v1/blobs (list)" "200" "$(code "$BASE_URL/internal/v1/blobs?limit=10" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"
log "GET /internal/v1/blobs/{id}" "200" "$(code "$BASE_URL/internal/v1/blobs/$BLOB_ID" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"
log "GET /internal/v1/blobs/{id}/download-url" "200" "$(code "$BASE_URL/internal/v1/blobs/$BLOB_ID/download-url" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"
log "GET /internal/v1/blobs/{id}/events" "200" "$(code "$BASE_URL/internal/v1/blobs/$BLOB_ID/events" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"

# Presign flow — on preprod (real HTTPS, not a docker-internal host) this should
# work end to end from any machine, unlike local dev.
request -X POST "$BASE_URL/internal/v1/blobs/presign" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS" \
  -H "Content-Type: application/json" \
  -d '{"filename":"smoke.txt","content_type":"text/plain"}'
log "POST /internal/v1/blobs/presign" "201" "$RESP_CODE"
UPLOAD_URL=$(echo "$RESP_BODY" | jq -r .upload_url 2>/dev/null)
PRESIGN_BLOB_ID=$(echo "$RESP_BODY" | jq -r .blob_id 2>/dev/null)

UPLOAD_PUT_CODE=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "$UPLOAD_URL" -H "Content-Type: text/plain" --data-binary @"$TMP_FILE")
log "PUT presigned upload_url" "200" "$UPLOAD_PUT_CODE"

COMPLETE_CODE=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/internal/v1/blobs/$PRESIGN_BLOB_ID/complete" \
  -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")
log "POST /internal/v1/blobs/{id}/complete" "200" "$COMPLETE_CODE"

# 2. Public routes
PATCH_PUBLIC=$(curl -sS -X PATCH "$BASE_URL/internal/v1/blobs/$PRESIGN_BLOB_ID" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS" -H "Content-Type: application/json" -d '{"visibility":"public"}')
PUBLIC_SLUG2=$(echo "$PATCH_PUBLIC" | jq -r .public_slug 2>/dev/null)
log "GET /v1/public/{ns}/{slug}/meta" "200" "$(code "$BASE_URL/v1/public/$NS/$PUBLIC_SLUG2/meta")"
log "GET /v1/public/{ns}/{slug}" "302" "$(code "$BASE_URL/v1/public/$NS/$PUBLIC_SLUG2")"
log "GET /v1/public/{ns}/{slug} unknown" "404" "$(code "$BASE_URL/v1/public/$NS/does-not-exist")"

# Cleanup this run's blobs so the namespace doesn't accumulate forever.
log "DELETE direct-upload blob" "204" "$(code -X DELETE "$BASE_URL/internal/v1/blobs/$BLOB_ID" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"
log "DELETE presigned blob" "204" "$(code -X DELETE "$BASE_URL/internal/v1/blobs/$PRESIGN_BLOB_ID" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"

# 3.3 Maintenance — always scoped to the smoke namespace, never omit `namespace=`.
log "POST /internal/v1/maintenance/purge-expired" "200" "$(code -X POST "$BASE_URL/internal/v1/maintenance/purge-expired?namespace=$NS" -H "X-Service-Api-Key: $SERVICE_API_KEY" -H "X-Blob-Namespace: $NS")"

echo "--- $FAIL_COUNT failing check(s) ---"
exit "$FAIL_COUNT"
