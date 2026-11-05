# CLAUDE.md — AI Resume Analyzer

You are the developer of this project. Dias is the product owner and reviewer: he describes
the outcome, you decide the implementation, build it, test it and open a PR.
Talk to Dias in Russian; write code, comments, commits, PRs and docs in English.

## Read first
- `docs/01-project-brief.md` — goal, scope (Definition of Done), hard constraints, metrics
- `docs/02-architecture.md` — target flow, data model, report JSON contract, repo layout
- `docs/03-working-agreement.md` — workflow, PR format, decision rules, Notion tracker
- `docs/04-references.md` — ideas to borrow and verified AWS facts
- `docs/05-operations.md` — alarms, DLQ check and what to do with failed messages
- `docs/decisions.md`, `docs/metrics.md` — keep these current

## Hard constraints (ask Dias before changing any of these)
- Fixed stack: S3, SQS + DLQ, Lambda (Python), Textract, Bedrock (Amazon Nova only),
  Bedrock Guardrails, DynamoDB, API Gateway, Cognito, KMS, IAM, CloudWatch,
  Terraform, GitHub Actions, pytest, Next.js. Region us-east-1.
- Budget ≈ $0: no NAT Gateway, no always-on resources, API throttling, cache before AI calls.
- All infrastructure as code. Nothing created by hand in the console (except infra/bootstrap,
  applied once by Dias).
- No AWS credentials in sessions; deploy only through GitHub Actions with OIDC.
- Security: least-privilege IAM per function, KMS encryption, no CV text or PII in logs.
- Logging: handlers never log document text or model output, not even at DEBUG or inside an
  exception message — only ids, sizes, counts, durations and status. Key redaction in
  `resume_analyzer.log` is only a safety net (it cannot see text inside a free-text message).
  Every handler gets a test like `backend/tests/test_no_content_in_logs.py`.
- Metrics are measured, never invented.

## How to work
- Small tasks: just do them. Large tasks: a 3–5 step plan first, then execute.
- If you see a simpler, faster or cheaper way inside the stack — propose it and apply it;
  record it in `docs/decisions.md`.
- Branch per task, small Conventional Commits, PR with a "How to check (phone-friendly)" list.
- Keep CI green; fix failures yourself.
- Update the Notion tracker (see working agreement) when a task starts, gets a PR, or is done.
- Never invent AWS API parameters; check the docs or say you are unsure.

## Commands (keep this section current as the repo grows)
Run from the repo root (`make help` lists targets).
- Install dev tools: `make install` (pinned in `backend/requirements-dev.txt`)
- Backend tests: `make test` (= `cd backend && pytest -q`)
- Lint: `make lint` (= `ruff check . && ruff format --check . && terraform -chdir=infra fmt -check -recursive`)
- Format: `make fmt`
- Infra validate (no AWS needed): `terraform -chdir=infra init -backend=false && terraform -chdir=infra validate`
- Infra plan/apply: CI only (`.github/workflows/ci.yml`): plan on every PR, apply on push to main.
  Backend bucket comes from repo variable `TF_STATE_BUCKET`:
  `terraform -chdir=infra init -backend-config="bucket=$TF_STATE_BUCKET"`
- Frontend (Node 22): `make web-install`, `make web-test` (tsc + `node --test`), `make web-build`
  (static export to `frontend/out`). Local dev: copy `frontend/config.example.json` to
  `frontend/public/config.json` with real stack outputs, then `make web-dev`.
  Deploy: CI job `deploy-frontend` after `apply` on main (S3 sync + CloudFront invalidation).
- Live Bedrock check (Dias, in AWS CloudShell; prints only counts/status):
  `cd backend && PYTHONPATH=src python3 scripts/bedrock_smoke.py`
- Live Guardrail check (Dias, in CloudShell; no model call, works with Nova quota 0; prints only
  actions): see the docstring of `backend/scripts/guardrail_smoke.py` (reads id/version from the Lambda env)
- process-analysis env: `ANALYSES_TABLE`, `CACHE_TABLE`, `BEDROCK_MODE` (`mock` default | `live`),
  `BEDROCK_MODEL_ID`, `BEDROCK_GUARDRAIL_ID`/`_VERSION`, `MAX_RECEIVE_COUNT`, `CACHE_TTL_SECONDS`
- Live API check (Dias, in CloudShell; prints only ids/status/score):
  `cd backend && API_URL=... CLIENT_ID=... SMOKE_EMAIL=... SMOKE_PASSWORD=... python3 scripts/api_smoke.py cv.pdf`
- DLQ check (Dias, in CloudShell; ~40 min between steps; prints only ids/counts):
  `cd backend && python3 scripts/dlq_check.py send`, later `python3 scripts/dlq_check.py check`
- Alarms: `infra/alarms.tf` (9 alarms, no actions); runbook `docs/05-operations.md`
- create-analysis env: `ANALYSES_TABLE`, `UPLOADS_BUCKET`, `UPLOADS_PREFIX`, `MAX_UPLOAD_BYTES`,
  `UPLOAD_URL_TTL_SECONDS`; read-analyses env: `ANALYSES_TABLE`
- API (HTTP API + Cognito JWT): `POST /analyses`, `GET /analyses?limit=&cursor=`,
  `GET /analyses/{analysis_id}`; outputs `api_url`, `cognito_user_pool_id`, `cognito_client_id`
- The Terraform registry may be blocked in cloud sessions; then CI is the source of truth for `validate`.
  Workaround: download `terraform` and `terraform-provider-aws` zips from releases.hashicorp.com, unpack the
  provider into `<mirror>/registry.terraform.io/hashicorp/aws/<ver>/linux_amd64/`, point `TF_CLI_CONFIG_FILE` at a
  `provider_installation { filesystem_mirror { path = "<mirror>" } }` file, then `init -backend=false` + `validate`
  in a copy of `infra/` (keeps `.terraform` out of the repo).
- Benchmarks for `docs/metrics.md` (`backend/scripts/benchmark.py`, prints only counts/timings/$):
  `local` (in-process handler latency, mock, no AWS), `cost` (cost model from list prices),
  `e2e cv.pdf --runs 10` (Dias, in CloudShell, same env as `api_smoke.py`; upload → DONE p50/p95)
