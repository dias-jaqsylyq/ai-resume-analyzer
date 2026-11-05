# CloudWatch alarms on failures (Definition of Done #6). Nine alarms, within the CloudWatch
# free tier of 10 standard-resolution alarms; one custom metric from a log metric filter.
#
# No alarm actions: SNS is outside the fixed stack. State is visible in the CloudWatch console
# (Alarms → "In alarm") and with `aws cloudwatch describe-alarms --state-value ALARM`.
# To get e-mails later, add an SNS topic and pass it as `alarm_actions` (needs the owner's OK).

locals {
  alarm_prefix = "${local.name}-"

  failed_analyses_metric = {
    namespace = "AiResumeAnalyzer"
    name      = "FailedAnalyses"
  }
}

# --- Queue: anything in the DLQ is an analysis that failed every retry ------------------------

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name        = "${local.alarm_prefix}analysis-dlq-not-empty"
  alarm_description = "Messages in ${aws_sqs_queue.analysis_dlq.name}: an upload failed ${var.max_receive_count} times. Inspect, then redrive or purge (docs/05-operations.md)."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.analysis_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching" # SQS stops sending metrics for an idle, empty queue
}

# --- Lambda: unhandled errors and throttles, per function --------------------------------------

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.functions

  alarm_name        = "${local.alarm_prefix}${replace(each.key, "_", "-")}-errors"
  alarm_description = "Unhandled errors (crash, timeout, out of memory) in ${each.value}."

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  depends_on = [aws_lambda_function.process_analysis, aws_lambda_function.api]
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = local.functions

  alarm_name        = "${local.alarm_prefix}${replace(each.key, "_", "-")}-throttles"
  alarm_description = "Throttled invocations of ${each.value} (account concurrency limit reached)."

  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  depends_on = [aws_lambda_function.process_analysis, aws_lambda_function.api]
}

# --- process-analysis: failures the handler catches -------------------------------------------
# The handler catches every exception (permanent ones are recorded, transient ones are reported
# back to SQS via batchItemFailures), so Lambda's Errors metric stays at 0 for them. This metric
# counts analyses that ended FAILED, from the structured log line "analysis failed".

resource "aws_cloudwatch_log_metric_filter" "failed_analyses" {
  name           = "${local.name}-failed-analyses"
  log_group_name = aws_cloudwatch_log_group.process_analysis.name
  pattern        = "{ ($.message = \"analysis failed\") && ($.last_attempt IS TRUE) }"

  metric_transformation {
    namespace     = local.failed_analyses_metric.namespace
    name          = local.failed_analyses_metric.name
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "failed_analyses" {
  alarm_name        = "${local.alarm_prefix}failed-analyses"
  alarm_description = "An analysis ended FAILED (permanent error, or last retry of a transient one). Logs: filter message = \"analysis failed\"."

  namespace           = local.failed_analyses_metric.namespace
  metric_name         = local.failed_analyses_metric.name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  depends_on = [aws_cloudwatch_log_metric_filter.failed_analyses]
}

# --- API: server-side errors -------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name        = "${local.alarm_prefix}api-5xx"
  alarm_description = "HTTP API ${aws_apigatewayv2_api.main.name} returned 5xx responses."

  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.main.id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
