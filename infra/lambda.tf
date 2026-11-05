# Lambda functions. The backend has no third-party runtime dependencies (boto3 ships with the
# Lambda Python runtime), so the package is just backend/src zipped.

data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/../backend/src"
  output_path = "${path.module}/build/backend.zip"
  excludes    = ["**/__pycache__/**"]
}

# --- process-analysis: SQS -> Textract -> Bedrock (mock|live) -> DynamoDB ------------------

resource "aws_cloudwatch_log_group" "process_analysis" {
  name              = "/aws/lambda/${local.functions.process_analysis}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "process_analysis" {
  function_name    = local.functions.process_analysis
  description      = "Extracts CV text with Textract and scores it against the job description"
  role             = aws_iam_role.lambda["process_analysis"].arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "resume_analyzer.handlers.process_analysis.handler"
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = var.process_timeout_seconds
  memory_size      = 256

  environment {
    variables = {
      ANALYSES_TABLE    = aws_dynamodb_table.analyses.name
      CACHE_TABLE       = aws_dynamodb_table.cache.name
      UPLOADS_PREFIX    = var.uploads_prefix
      MAX_RECEIVE_COUNT = tostring(var.max_receive_count) # must equal the queue's redrive maxReceiveCount
      BEDROCK_MODE      = var.bedrock_mode
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      # Used only in live mode; mock mode makes no Bedrock call at all.
      BEDROCK_GUARDRAIL_ID      = aws_bedrock_guardrail.analysis.guardrail_id
      BEDROCK_GUARDRAIL_VERSION = aws_bedrock_guardrail_version.analysis.version
      LOG_LEVEL                 = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.process_analysis, aws_iam_role_policy.lambda]
}

resource "aws_lambda_event_source_mapping" "process_analysis" {
  event_source_arn        = aws_sqs_queue.analysis.arn
  function_name           = aws_lambda_function.process_analysis.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  # At most 2 CVs in parallel (the minimum allowed): protects Textract/Bedrock quotas and cost.
  scaling_config {
    maximum_concurrency = 2
  }
}
