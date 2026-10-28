# Decisions

| Date | Decision | Why | Alternative considered |
| --- | --- | --- | --- |
| 2026-10-28 | Region us-east-1 | Nova Lite/Micro available in-region; Textract available | ap-southeast-1 (closer to HK, but Nova via cross-region only) |
| 2026-10-28 | Amazon Nova models only | Covered by AWS credits; budget ≈ $0 | Claude on Bedrock (billed via Marketplace, not covered by credits) |
| 2026-10-28 | Deploy via GitHub Actions + OIDC | No long-lived AWS keys anywhere; works from phone | AWS keys in cloud session env vars |
