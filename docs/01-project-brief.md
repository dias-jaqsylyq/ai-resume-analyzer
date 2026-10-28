# 01 — Project Brief: AI Resume Analyzer

## What we are building
A service that analyzes a CV (PDF) against a job description and returns a structured report:
- **ATS score** (0–100) with a short rationale
- **Skills match**: matched skills, missing skills, nice-to-have gaps
- **Suggestions**: concrete, prioritized edits to the CV
- **History**: past analyses per user

It is a production-style, event-driven AWS pipeline — not a notebook demo. Upload triggers text
extraction, a foundation model scores the CV against the job description, and results are stored
and served through an authenticated API and a web dashboard, with retries, encryption of personal
data and cost controls.

## Why it exists
A portfolio project for Cloud / Backend + AI roles. It must show solid cloud engineering
(queues, retries, idempotency, encryption, IaC, CI/CD, observability) combined with GenAI.
The project is built with Claude Code acting as the developer; the owner (Dias) directs and reviews.

## Users (for now)
Single owner using it on his own CV. Public launch and open-sourcing are out of scope for this
version, but the design should not block multi-user use later (Cognito user pools, per-user
data partitioning).

## Scope — Definition of Done
Source: Notion card "AI Resume Analyzer: Event-Driven Document Intelligence Pipeline".
1. Terraform for S3, queue, Lambdas, DynamoDB, API and auth
2. Upload → extraction → analysis flow with retries and a DLQ
3. Structured score report (ATS, skills match, suggestions) stored per user
4. Dashboard (Next.js)
5. KMS encryption and lifecycle deletion of uploads
6. CloudWatch alarms on failures
7. Cost per 100 CVs documented in the README

### Additions agreed by the owner
- CI/CD with GitHub Actions (lint, tests, terraform plan on PR, apply on merge, OIDC — no static keys)
- Bedrock Guardrails: prompt-injection defence (CV text is untrusted input) and PII filtering
- Result cache keyed by SHA-256 of (CV bytes + job description) with DynamoDB TTL
- pytest unit tests with mocks
- Pre-signed URL upload directly to S3
- Structured JSON logging with a correlation ID across all functions
- Textract output converted to clean Markdown/text before it is sent to the model

## Out of scope (this version)
Public launch, billing, LaTeX (.tex) input, CV rewriting/generation, multi-language UI,
custom ML training.

## Hard constraints
- **Fixed stack** (these are CV keywords — do not swap them):
  S3, SQS + DLQ, Lambda (Python), Textract, Bedrock (Amazon Nova models), Bedrock Guardrails,
  DynamoDB, API Gateway, Cognito, KMS, IAM, CloudWatch, Terraform, GitHub Actions, pytest, Next.js.
- **Budget ≈ $0**: Amazon Nova models only (third-party Bedrock models are billed via AWS
  Marketplace and are not covered by AWS credits); no NAT Gateway; no always-on resources;
  API throttling; Textract DetectDocumentText (not Forms/Tables).
- **Region**: us-east-1.
- **Security**: least-privilege IAM for every function; encryption at rest; no CV text or PII
  in logs; only synthetic CVs or the owner's own CV.

## Success metrics (must be measured, never invented)
Recorded in `docs/metrics.md` with value, how it was measured, and date:
- Number of AWS resources managed by Terraform; time to deploy from zero
- End-to-end latency p50 / p95 (upload → report ready)
- Cost per CV and per 100 CVs
- Cache savings on repeat uploads (% tokens / $ saved)
- Processing success rate over N CVs; messages correctly routed to the DLQ
- Prompt-injection test cases blocked (X / Y)
- Number of tests and coverage %; CI pipeline duration
- Score stability: variance of the ATS score across repeated runs on the same CV

## Final deliverable for the owner's CV
3–4 bullet points in the form "action + technology + measured result", written only from
`docs/metrics.md`, plus a LaTeX version for Overleaf.
