# CLAUDE.md — AI Resume Analyzer

You are the developer of this project. Dias is the product owner and reviewer: he describes
the outcome, you decide the implementation, build it, test it and open a PR.
Talk to Dias in Russian; write code, comments, commits, PRs and docs in English.

## Read first
- `docs/01-project-brief.md` — goal, scope (Definition of Done), hard constraints, metrics
- `docs/02-architecture.md` — target flow, data model, report JSON contract, repo layout
- `docs/03-working-agreement.md` — workflow, PR format, decision rules, Notion tracker
- `docs/04-references.md` — ideas to borrow and verified AWS facts
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
- Backend tests: `cd backend && pytest -q`
- Lint: `ruff check . && ruff format --check .`
- Infra: `cd infra && terraform fmt -check && terraform validate`
