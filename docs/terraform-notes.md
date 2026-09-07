# Terraform notes — butter_blob

Infra for butter_blob lives in the sibling **`../infra`** repo, not here.

## Public CDN (`../infra/terraform/staging/cdn_blob.tf`) — prompt 15

Design **B** (see `docs/spec.md` §8.4): CloudFront in front of the **private** S3
bucket via Origin Access Control. Resources created:

| Resource | Purpose |
|---|---|
| `aws_s3_bucket.blob` + `aws_s3_bucket_public_access_block.blob` + `aws_s3_bucket_ownership_controls.blob` | the object store butter_blob writes to (`S3_BUCKET`); stays private |
| `aws_cloudfront_origin_access_control.blob` | signs CloudFront → S3 origin requests (SigV4) |
| `aws_cloudfront_cache_policy.blob` | honors object `Cache-Control`, no cookies/headers, `response-content-disposition` in the cache key |
| `aws_acm_certificate.blob` (+ `_validation`, `provider = aws.us_east_1`) | TLS cert for `blob.devbutter.tech` — CloudFront certs must be in us-east-1 |
| `aws_cloudfront_distribution.blob` | the edge; alias `blob.devbutter.tech`, `GET`/`HEAD` only, `redirect-to-https` |
| `aws_iam_policy_document.blob_bucket` + `aws_s3_bucket_policy.blob` | grants the distribution (and only it, via `AWS:SourceArn`) `s3:GetObject` |
| `aws_route53_record.blob_public` (A/alias) + `aws_route53_record.blob_cert_validation` | DNS for the domain and for ACM validation |

Outputs: `blob_cdn_distribution_id`, `blob_cdn_domain`, `blob_bucket`.

### Wiring into the service

Set on the ECS task (staging):

```
PUBLIC_CDN_BASE_URL=https://blob.devbutter.tech
CLOUDFRONT_DISTRIBUTION_ID=<output blob_cdn_distribution_id>
S3_BUCKET=<output blob_bucket>          # must match the bucket above
```

The task role also needs `cloudfront:CreateInvalidation` on that distribution
(for `app/core/cdn.py::invalidate`).

### Apply

```
cd ../infra/terraform/staging
terraform init
terraform plan   # expect only the new aws_s3_bucket.blob / cloudfront / acm / route53 resources
terraform apply
```

`terraform validate` and `terraform fmt` pass in this tree. `terraform plan`
needs the `devbutter-nonprod` AWS SSO profile and a real `devbutter.tech`
Route53 hosted zone (looked up via `data "aws_route53_zone"`).

### Local dev

No CDN. Leave `PUBLIC_CDN_BASE_URL` and `CLOUDFRONT_DISTRIBUTION_ID` empty —
public blobs are served as presigned MinIO URLs and `cdn.invalidate` is a no-op.
