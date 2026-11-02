# Main stack for AI Resume Analyzer. Deployed only by GitHub Actions (plan on PR, apply on main).
# Core data plane (RA-6): kms.tf, s3.tf, sqs.tf, dynamodb.tf, iam.tf.
# API (RA-15): cognito.tf, api.tf. Frontend hosting (RA-19): frontend.tf. Alarms come later.

data "aws_caller_identity" "current" {}

locals {
  name       = "ai-resume-analyzer"
  account_id = data.aws_caller_identity.current.account_id

  uploads_bucket_name = "${local.name}-uploads-${local.account_id}"
  uploads_bucket_arn  = "arn:aws:s3:::${local.uploads_bucket_name}"

  # Lambda function names are fixed here so IAM can scope log permissions before the functions exist.
  functions = {
    create_analysis  = "${local.name}-create-analysis"
    process_analysis = "${local.name}-process-analysis"
    read_analyses    = "${local.name}-read-analyses"
  }
}
