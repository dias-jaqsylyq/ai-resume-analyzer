# Decisions

| Date | Decision | Why | Alternative considered |
| --- | --- | --- | --- |
| 2026-10-28 | Region us-east-1 | Nova Lite/Micro available in-region; Textract available | ap-southeast-1 (closer to HK, but Nova via cross-region only) |
| 2026-10-28 | Amazon Nova models only | Covered by AWS credits; budget ≈ $0 | Claude on Bedrock (billed via Marketplace, not covered by credits) |
| 2026-10-28 | Deploy via GitHub Actions + OIDC | No long-lived AWS keys anywhere; works from phone | AWS keys in cloud session env vars |
| 2026-10-28 | Bootstrap stack with local state | It creates the remote-state bucket itself; applied once by the owner | Click-ops in the console |
| 2026-10-28 | GitHub OIDC role trusted only for this repo's `main` and pull requests | No long-lived keys; other repos/branches cannot assume it | Wildcard `repo:owner/*` trust |
| 2026-10-28 | Deploy role temporarily has AdministratorAccess | Speed for a single-owner private repo; narrowing tracked as backlog task RA-24 | Hand-written least-privilege policy up front |
| 2026-10-28 | S3 native state locking (`use_lockfile`) instead of DynamoDB lock table | Fewer resources, supported since Terraform 1.10 | DynamoDB lock table |
| 2026-10-28 | OIDC trust matches GitHub's immutable subject (`repo:owner@ID/repo@ID:...`) with `StringEquals` | The repo uses `use_immutable_subject`; name-only `sub` was rejected (AccessDenied in CloudTrail). IDs also block repo-rename / name-reuse attacks | Name-only `sub` with wildcards |
| 2026-10-28 | One `ci` workflow; `aws-oidc-check` merged into the plan/apply jobs (they run `sts get-caller-identity`) | One place for PR checks; OIDC is still verified on every PR and every push to main | Keep a separate OIDC check workflow |
| 2026-10-28 | Main stack backend uses partial config: bucket passed with `-backend-config` from `vars.TF_STATE_BUCKET` | Bucket name contains the account ID; keeps it out of the repo and in one place | Hard-code the bucket name in `versions.tf` |
| 2026-10-28 | Apply on main re-plans and applies that saved plan; no GitHub environment on the apply job | The OIDC trust allows only `ref:refs/heads/main` and `pull_request` subjects; an environment would change the `sub` claim and be denied | Manual approval via a protected environment (needs a trust-policy change) |
| 2026-10-28 | Ruff config in root `ruff.toml`; tool versions pinned in `backend/requirements-dev.txt` | Same rules for all Python in the repo; local and CI results match | Config inside `backend/pyproject.toml` |
| 2026-10-28 | Shared JSON logger written on the standard library (`backend/src/resume_analyzer/log.py`), not AWS Lambda Powertools | Zero runtime dependencies and nothing to package per Lambda; we need only JSON lines, a correlation ID and Lambda context fields. Redacts CV/PII keys as a safety net | Powertools Logger (extra dependency/layer for a small feature set) |
| 2026-10-28 | Textract async API (`StartDocumentTextDetection` + `GetDocumentTextDetection`) polled from the `process-analysis` Lambda, with backoff and a stop 10 s before the Lambda deadline | Sync `DetectDocumentText` takes only single-page PDFs; a CV job finishes in seconds, so no SNS topic or second Lambda is needed | SNS completion notification + a separate Lambda |
| 2026-10-28 | Textract `ClientRequestToken` = SHA-256 of bucket/key/ETag | An SQS retry reuses the same Textract job instead of starting (and paying for) a new one | No token (every retry re-runs OCR) |
| 2026-10-28 | Upload key layout `uploads/<user_sub>/<analysis_id>.pdf`; uploads over 5 MiB rejected before Textract | The S3 event alone gives the user partition and the correlation ID; the size check avoids OCR cost on junk | Look the analysis up in DynamoDB by key |
| 2026-10-28 | AWS calls in tests are mocked with botocore `Stubber` on a pinned `boto3` (dev-only; the Lambda runtime ships boto3) | Stubber validates every request against the real API model, so invented parameters fail the tests; no extra mocking library | moto |
| 2026-10-28 | Every handler has a test that runs it on a synthetic CV at DEBUG and fails if any of the text reaches logs or stdout | Key-based redaction cannot catch text inside a free-text message | Rely on redaction and code review |
