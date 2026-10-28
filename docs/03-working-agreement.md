# 03 — Working Agreement

## Roles
- **Claude (Claude Code sessions and the Claude Project)** — the developer and architect.
  Decides *how* to implement, writes all code, tests and docs, runs checks, opens PRs.
- **Dias** — the product owner and reviewer. Describes *what* is needed and the expected result,
  reviews PRs (often from a phone), runs the few steps that need his AWS admin access, merges.

## Language
Talk to Dias in Russian. Code, comments, commit messages, PR descriptions and README in English.

## How a task flows
1. Dias describes the outcome ("I want to upload my CV and see a report within a minute").
2. Claude replies with a short plan (3–5 steps) only for large tasks; small tasks start directly.
3. Claude works on a branch, commits in small steps (Conventional Commits:
   `feat:`, `fix:`, `infra:`, `test:`, `docs:`, `ci:`), runs tests, opens a PR.
4. Every PR description has: what changed and why, how it was tested, and a
   **"How to check (phone-friendly)"** checklist of 2–5 items Dias can verify without a laptop.
5. CI must be green before merge. Claude fixes CI failures itself (auto-fix).
6. After merge, Claude updates the Notion tracker and the docs.

## Decision rules
- Inside the fixed stack (see 01-project-brief.md) Claude chooses freely and proposes simpler,
  faster or cheaper options when it sees them — and applies them.
- Ask Dias only when: a hard constraint would change, money could be spent, AWS console/admin
  access or credentials are needed, or a choice is irreversible.
- Never invent AWS API parameters or service limits; if unsure, check the docs or say so.
- Never put AWS credentials in the cloud session environment. Deployments run only in
  GitHub Actions via OIDC.

## Records Claude keeps up to date
- `docs/decisions.md` — one entry per significant decision: decision, why, alternative considered.
- `docs/metrics.md` — measured numbers only: metric, value, how measured (script/command), date.
- `README.md` — what it is, architecture diagram, how to deploy, cost per 100 CVs, references.

## Notion tracker
- Page: "AI Resume Analyzer — Build Tracker" →
  https://app.notion.com/p/407204d51b158137b6f4d392e1dd713b
- Tasks database (data source `collection://1ba15de6-9b95-4bea-a959-05f9a9fab37d`).
  Properties: Task, Status (Backlog / To do / In progress / In review / Done / Blocked),
  Phase, Day, Owner (Claude / Dias), PR (url), Notes.
- When starting a task → In progress. PR opened → In review + PR link. Merged → Done.
  Waiting on Dias/AWS → Blocked with a one-line reason in Notes.
- Add new tasks when work is discovered. Keep titles short and outcome-focused.
- If the Notion connector is not available in a session, list the status changes at the end of
  the reply so they can be applied from the Claude Project.

## Definition of done for any task
Code + tests pass in CI, docs/decisions updated if a decision was made, metrics recorded if
something was measured, tracker updated, phone-friendly check list in the PR.
