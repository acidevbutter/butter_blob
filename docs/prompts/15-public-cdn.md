# Prompt 15 — CDN / custom domain for `/v1/public/*`

**Status:** ⬜ not started · **Runner:** Codex · **Phase:** 2 · **Edits:** `../infra` + small app change.

## Goal
Serve public blobs from a cache/edge at `blob.devbutter.tech` instead of handing
out raw presigned S3 URLs, and set sane cache headers.

## Depends on
09.

## Reference
`../infra/terraform/staging/main.tf` (resource enumeration style, S3 bucket +
public-access-block patterns), `docs/spec.md` §8.4, §11.

## Design decision to record in `docs/spec.md`
Pick one and document the trade-off:
- **A. CloudFront in front of the butter_blob service** — origin is the ECS
  service; CloudFront caches the `302` + (optionally) follows it. Simple app side;
  the redirect target is still a short-lived presigned URL, so caching the 302 is
  near useless. Reject unless we make the public route stream bytes (it currently
  doesn't).
- **B. CloudFront in front of the S3 bucket, OAC** — the public route returns a
  stable CDN URL (`https://blob.devbutter.tech/<key>`) instead of a presigned S3
  URL; CloudFront reads the object via Origin Access Control; the bucket stays
  private. Cache key = the object key. **Recommended.** Requires the public route
  to know the CDN base and to emit CDN URLs for `public` blobs; invalidation on
  delete/replace.

## Files
- `infra/terraform/staging/` — `aws_cloudfront_distribution` (B), `aws_cloudfront_origin_access_control`,
  ACM cert (us-east-1) for `blob.devbutter.tech`, `aws_route53_record` CNAME,
  bucket policy granting the OAC `s3:GetObject`, a cache policy (honor
  `Cache-Control`, no cookies, vary on `response-content-disposition` query).
- `butter_blob/app/settings/config.py` — `public_cdn_base_url: str = ""`. When set,
  `PublicService` builds `f"{public_cdn_base_url}/{blob.key}"` for the redirect
  target of a **non-temporary** `stored` public blob; temporary blobs keep the
  short presigned URL (don't cache those).
- `butter_blob/app/public/router.py` / `service.py` — set response headers on the
  `302` and on `/meta`: `Cache-Control: public, max-age=86400` for permanent public
  blobs, `Cache-Control: no-store` for temporary. `BlobRead.public_url` /
  `producer-contract.md` use the CDN base when configured.
- `butter_blob/app/blobs/service.py` — on `DELETE` / visibility→private / content
  replace of a public blob, call a new `app/core/cdn.py::invalidate(paths)` (no-op
  when `public_cdn_base_url` unset; CloudFront `create_invalidation` otherwise).
- `docs/terraform-notes.md` + `docs/spec.md` §8.4/§10 updated.

## Acceptance
- `terraform plan` in `infra/terraform/staging` shows only the intended new
  resources.
- `butter_blob` tests: with `public_cdn_base_url` set, `GET /v1/public/{ns}/{slug}`
  for a permanent public blob → `302` to `https://cdn.../<key>` and
  `Cache-Control: public, max-age=...`; a temporary public blob → presigned URL +
  `no-store`.
- `invalidate()` called on delete of a public blob (mock CloudFront).
- `ruff` / `mypy` / `pytest` green.

## Notes
No CDN in local dev — everything stays on presigned MinIO URLs when
`public_cdn_base_url` is empty.
