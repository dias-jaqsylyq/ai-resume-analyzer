# Main stack for AI Resume Analyzer. Deployed only by GitHub Actions (plan on PR, apply on main).
# Resources (S3 uploads, SQS + DLQ, Lambdas, DynamoDB, API, Cognito) are added in later tasks.

data "aws_caller_identity" "current" {}
