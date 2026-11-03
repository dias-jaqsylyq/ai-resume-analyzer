# 02 — Target Architecture

This is the intended design. Claude may improve implementation details inside the fixed stack;
any change to the flow below is recorded in `docs/decisions.md`.

## Request flow
```
Browser (Next.js on S3 + CloudFront)
   │  1. sign in (Cognito)
   │  2. POST /analyses {job_description} → API Gateway (Cognito authorizer, throttling)
   │        → Lambda "create-analysis": writes PENDING item, returns pre-signed S3 POST
   │     (policy enforces application/pdf and ≤ 5 MiB)
   │  3. POST CV.pdf directly to S3 (uploads bucket, KMS, lifecycle expiry)
   ▼
S3 ObjectCreated event → SQS "analysis-queue" (redrive → DLQ after N attempts)
   ▼
Lambda "process-analysis" (SQS trigger, batch size 1, partial batch failures)
   a. idempotency check + cache lookup by SHA-256(CV bytes + JD)
   b. Textract DetectDocumentText (async API for multi-page PDFs) → clean text/Markdown
   c. Bedrock Converse API, Amazon Nova model, with Guardrails attached
      (prompt-attack filter on CV text, PII filter) → JSON
   d. validate JSON against schema; retry once on invalid output; else fail → DLQ
   e. write result to DynamoDB (status DONE), write cache entry with TTL
   ▼
GET /analyses, GET /analyses/{id} → Lambda "read-analyses" → DynamoDB (per-user partition)
```

## Data model (DynamoDB, on-demand)
- `analyses`: PK `USER#<sub>`, SK `ANALYSIS#<ulid>`; status (PENDING | PROCESSING | DONE | FAILED),
  created_at, job_title, result (score, matched_skills, missing_skills, suggestions), error.
- `cache`: PK `<sha256>`; result; `expires_at` (TTL attribute).

## Report JSON (contract between model, backend and frontend)
```json
{
  "ats_score": 0,
  "score_rationale": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "suggestions": [{"priority": "high|medium|low", "section": "string", "advice": "string"}],
  "summary": "string"
}
```

## Cross-cutting
- **Security**: one IAM role per Lambda, least privilege; KMS key for S3 and DynamoDB;
  bucket blocks public access; CV text never logged; Guardrails on every model call.
- **Observability**: JSON logs with `correlation_id` (analysis id) carried via S3 object
  metadata and SQS message; CloudWatch alarms on Lambda errors and DLQ depth > 0.
- **Cost**: no VPC/NAT, no provisioned capacity, API throttling, small Nova model,
  cache before calling Textract/Bedrock, uploads expire automatically.
- **Infra layout**: `infra/bootstrap` (state bucket, OIDC, deploy role — applied once locally),
  `infra/` main stack with remote state in S3 (native lockfile).
- **CI/CD**: PR → lint, pytest, `terraform fmt/validate/plan`; merge to main → `terraform apply`
  and frontend deploy, authenticated with GitHub OIDC.

## Repository layout (suggested)
```
backend/      Lambda handlers + shared lib, tests/
infra/        Terraform (bootstrap/, modules/, main stack)
frontend/     Next.js app (static export)
scripts/      benchmark and helper scripts
docs/         brief, architecture, decisions.md, metrics.md
.github/      workflows
```
