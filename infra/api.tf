# User-facing API: HTTP API (API Gateway v2) with a Cognito JWT authorizer and throttling.
#   POST /analyses                 -> create-analysis (PENDING item + pre-signed S3 POST)
#   GET  /analyses                 -> read-analyses   (history, newest first)
#   GET  /analyses/{analysis_id}   -> read-analyses   (one analysis + report)
# The package (data.archive_file.backend) and the execution roles come from lambda.tf / iam.tf.

locals {
  api_functions = {
    create_analysis = {
      description = "POST /analyses: creates a PENDING analysis and a pre-signed CV upload"
      handler     = "resume_analyzer.handlers.create_analysis.handler"
      env = {
        UPLOADS_BUCKET         = aws_s3_bucket.uploads.bucket
        UPLOADS_PREFIX         = var.uploads_prefix
        MAX_UPLOAD_BYTES       = tostring(var.max_upload_bytes)
        UPLOAD_URL_TTL_SECONDS = tostring(var.upload_url_ttl_seconds)
      }
    }
    read_analyses = {
      description = "GET /analyses[/{id}]: a user's analysis history and reports"
      handler     = "resume_analyzer.handlers.read_analyses.handler"
      env         = {}
    }
  }

  api_routes = {
    "POST /analyses"              = "create_analysis"
    "GET /analyses"               = "read_analyses"
    "GET /analyses/{analysis_id}" = "read_analyses"
  }
}

# --- Lambdas -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  for_each = local.api_functions

  name              = "/aws/lambda/${local.functions[each.key]}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  for_each = local.api_functions

  function_name    = local.functions[each.key]
  description      = each.value.description
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = each.value.handler
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = merge(
      { ANALYSES_TABLE = aws_dynamodb_table.analyses.name, LOG_LEVEL = "INFO" },
      each.value.env,
    )
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.lambda]
}

resource "aws_lambda_permission" "api" {
  for_each = local.api_functions

  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# --- HTTP API ----------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "main" {
  name          = local.name
  protocol_type = "HTTP"
  description   = "AI Resume Analyzer user API (Cognito JWT)"

  cors_configuration {
    allow_origins = local.allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  # Access tokens have no `aud`; API Gateway then checks `client_id` against the audience.
  jwt_configuration {
    issuer   = "https://${aws_cognito_user_pool.main.endpoint}"
    audience = [aws_cognito_user_pool_client.web.id]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  for_each = local.api_functions

  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api[each.key].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "api" {
  for_each = local.api_routes

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.api[each.value].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate
    throttling_burst_limit = var.api_throttle_burst
  }

  # Each new analysis can start a Textract + Bedrock run, so creation is throttled harder.
  route_settings {
    route_key              = "POST /analyses"
    throttling_rate_limit  = var.create_throttle_rate
    throttling_burst_limit = var.create_throttle_burst
  }

  depends_on = [aws_apigatewayv2_route.api]
}

# --- Browser upload to S3 (pre-signed POST from create-analysis) -------------------------

resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = local.allowed_origins
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
