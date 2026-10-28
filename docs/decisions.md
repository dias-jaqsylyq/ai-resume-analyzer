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
