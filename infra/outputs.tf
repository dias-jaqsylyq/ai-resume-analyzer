output "account_id" {
  description = "AWS account the stack is deployed to (confirms the OIDC role works)"
  value       = data.aws_caller_identity.current.account_id
}

output "kms_key_arn" {
  description = "Project-wide customer managed KMS key"
  value       = aws_kms_key.main.arn
}

output "uploads_bucket" {
  description = "S3 bucket for CV uploads"
  value       = aws_s3_bucket.uploads.bucket
}

output "analysis_queue_url" {
  description = "SQS queue fed by S3 upload events"
  value       = aws_sqs_queue.analysis.url
}

output "analysis_dlq_url" {
  description = "Dead-letter queue for failed analyses"
  value       = aws_sqs_queue.analysis_dlq.url
}

output "analyses_table" {
  description = "DynamoDB table with analyses per user"
  value       = aws_dynamodb_table.analyses.name
}

output "cache_table" {
  description = "DynamoDB result cache (TTL on expires_at)"
  value       = aws_dynamodb_table.cache.name
}

output "lambda_role_arns" {
  description = "Execution role ARN per Lambda function"
  value       = { for k, r in aws_iam_role.lambda : k => r.arn }
}
