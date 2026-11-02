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

output "process_analysis_function" {
  description = "Lambda that consumes the analysis queue"
  value       = aws_lambda_function.process_analysis.function_name
}

output "bedrock_mode" {
  description = "Whether process-analysis calls Bedrock (live) or the deterministic mock"
  value       = var.bedrock_mode
}

output "api_url" {
  description = "Base URL of the user API"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool for sign-in"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Public Cognito app client for the web app"
  value       = aws_cognito_user_pool_client.web.id
}
