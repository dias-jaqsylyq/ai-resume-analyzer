# 04 — References and Ideas to Borrow

Use these as inspiration only — write our own code. Credit them in the README.

| Source | What to borrow |
| --- | --- |
| [seehiong/ats-buddy](https://github.com/seehiong/ats-buddy) | Hash-based result cache in DynamoDB with 24h TTL; Bedrock Nova Lite for ATS analysis; PII redaction idea (we use Bedrock Guardrails instead of S3 Object Lambda + Comprehend). |
| [GladiHimself/SkillMap](https://github.com/GladiHimself/SkillMap) | Pre-signed URL upload straight to S3; S3 → SQS → Lambda → Bedrock flow; Terraform-only infra; GitHub Actions CI/CD; correlation IDs carried in S3 object metadata; structured JSON logs. |
| [AWS blog: AI recruitment assistant on Bedrock](https://aws.amazon.com/blogs/machine-learning/build-an-ai-powered-recruitment-assistant-using-amazon-bedrock/) | Bedrock Guardrails to anonymise PII and block prompt injection coming from CV text; Converse API with Amazon Nova. |
| [aws-samples/intelligent-document-processing-with-amazon-bedrock](https://github.com/aws-samples/intelligent-document-processing-with-amazon-bedrock) | Async Textract for multi-page PDFs; format OCR output (amazon-textract-textractor) as Markdown before sending to the model. |
| [deansmile/Scalable-Resume-Ranking](https://github.com/deansmile/Scalable-Resume-Ranking) | Modular Lambda microservices; pre-signed URLs; resume parsing via Textract. |

## Useful AWS facts (verified Oct 2026)
- Bedrock serverless models no longer need manual enablement — the Model access page was retired
  ([AWS Security Blog](https://aws.amazon.com/blogs/security/simplified-amazon-bedrock-model-access)).
- Nova Lite / Nova Micro are available in-region in us-east-1
  ([Bedrock regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html)).
- AWS promotional credits do not cover AWS Marketplace charges; third-party models on Bedrock
  (e.g. Claude) are billed through Marketplace → use Amazon Nova only.
- Textract free tier: 3 months for new customers, 1,000 pages/month DetectDocumentText
  ([Textract pricing](https://aws.amazon.com/textract/pricing/)).

## Claude Code cloud sessions
- Docs: [Use Claude Code in the cloud](https://code.claude.com/docs/en/claude-code-on-the-web.md),
  [Cloud environments](https://code.claude.com/docs/en/cloud-environments.md).
- Default network level is Trusted (package registries + allowlist). MCP connectors (e.g. Notion)
  work without allowlisting. Terraform `validate/plan` may not be runnable in the session — CI
  is the source of truth for infra checks.
