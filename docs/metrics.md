# Metrics

Only measured values. Every row says how it was measured so it can be reproduced.
Estimates (cost model) are kept in a separate section and are labelled as such.
Rows marked **pending** need a run on the deployed stack by the owner (commands given).

## Measured

| Metric | Value | How measured | Date |
| --- | --- | --- | --- |
| AWS resources managed by Terraform (main stack) | 62 | `resource` blocks × `for_each` keys in `infra/*.tf` at `c252891` (48 blocks; 9 use `for_each` over the 3 functions / 2 API functions / 3 routes); cross-check: the last apply (PR #11) added 10 alarms/filters | 2026-11-05 |
| AWS resources in the bootstrap stack (state bucket, OIDC, deploy role) | 8 | `resource` blocks in `infra/bootstrap/main.tf` (no `for_each`) | 2026-11-05 |
| Backend unit tests | 142 passed | `cd backend && python3 -m pytest -q` (includes 5 tests for `scripts/benchmark.py`) | 2026-11-05 |
| Backend statement coverage | 97% (774 statements, 26 missed) | `cd backend && python3 -m coverage run --source=src -m pytest -q && python3 -m coverage report` (coverage 7.17.2, not part of CI) | 2026-11-05 |
| Frontend unit tests | 16 passed | `cd frontend && npm test` (`node --test`) | 2026-11-05 |
| CI duration, pull request | p50 67 s, max 93 s (n = 10) | GitHub Actions run wall clock (created → completed) of the last 10 `ci` runs on PRs (#4–#12); jobs: ruff + pytest, frontend typecheck/tests/build, terraform fmt/validate/plan | 2026-11-05 |
| CI duration, push to main (checks + apply + frontend deploy) | p50 106 s, max 267 s (n = 5) | Same, last 5 `ci` runs on `main` (#5, #8, #9, #10, #11 merges). Max = PR #10, which created the CloudFront distribution | 2026-11-05 |
| process-analysis own compute, mock mode, cache miss | p50 0.14 ms, p95 0.16 ms (n = 1000) | `cd backend && PYTHONPATH=src python3 scripts/benchmark.py local --runs 1000`: the real handler in-process with Textract and DynamoDB replaced by in-memory fakes, 1-page synthetic CV. Excludes every AWS round trip; shows the code itself adds < 1 ms | 2026-11-05 |
| process-analysis own compute, cache hit | p50 0.02 ms, p95 0.02 ms (n = 1000) | Same run, same file + same JD under a new analysis id (Textract and the analyzer are skipped) | 2026-11-05 |
| End-to-end latency, upload → DONE, mock mode, cache miss | **pending** | Owner in CloudShell: `cd backend && python3 scripts/benchmark.py e2e cv.pdf --runs 10` (p50/p95 printed; 1 s polling) | — |
| End-to-end latency, upload → DONE, cache hit | **pending** | Same run, last line | — |
| Processing success rate over N CVs | **pending** | Same run, `success: X/N` line | — |
| Messages correctly routed to the DLQ | **pending** | `scripts/dlq_check.py send`, ~40 min later `check` (`docs/05-operations.md`) | — |
| Time to deploy from zero | **pending** | Time of the CI `apply` + `deploy-frontend` jobs on an empty account/state (after `terraform destroy`) | — |
| Bedrock tokens per analysis, score stability, prompt-injection cases blocked | **pending** (needs `BEDROCK_MODE=live`) | Blocked by the Nova daily token quota (0, AWS case open); guardrail smoke check `scripts/guardrail_smoke.py` (PR #12) | — |

## Estimates (cost model, not a bill)

`cd backend && PYTHONPATH=src python3 scripts/benchmark.py cost` — request counts per analysis
come from the code (see the comments in `scripts/benchmark.py`), prices are AWS on-demand list
prices for us-east-1 read from the AWS Price List API on 2026-11-05. Free tiers are ignored, so
this is the cost **after** they run out. Assumptions: process-analysis billed for 8 s in mock mode
(mostly waiting for the Textract job) and 15 s in live mode, 256 MB arm64; the dashboard polls
about 5 times; a 2-page CV is ~6,000 characters of text.

| Scenario | Per CV | Per 100 CVs | Largest part |
| --- | --- | --- | --- |
| Mock mode, 1-page CV | $0.0016 | $0.16 | Textract $0.0015 / page |
| Mock mode, 2-page CV | $0.0031 | $0.31 | Textract |
| Live, Nova Lite, 2-page CV, typical (~2,800 input + 800 output tokens) | $0.0034 | $0.34 | Textract; Nova adds ~$0.0004 |
| Live, Nova Lite, 2-page CV, worst case (retry + 2 × 2,000 output tokens) | $0.0044 | $0.44 | Textract |
| Cache hit (same CV + same JD within 24 h) | $0.00004 | $0.004 | DynamoDB |

Fixed monthly cost at idle: the one KMS key ($1/month) plus a few cents of S3 storage;
everything else is pay-per-request. Textract's free tier (new accounts, first 3 months) covers
1,000 pages/month, so the first ~500 two-page CVs a month cost about $0.
