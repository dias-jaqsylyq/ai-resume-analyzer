# Analysis queue (S3 events -> process-analysis Lambda) with a dead-letter queue.

resource "aws_sqs_queue" "analysis_dlq" {
  name                              = "${local.name}-analysis-dlq"
  message_retention_seconds         = 1209600 # 14 days (max) to inspect failures
  kms_master_key_id                 = aws_kms_key.main.arn
  kms_data_key_reuse_period_seconds = 86400 # max reuse = fewest KMS calls
}

resource "aws_sqs_queue" "analysis" {
  name                              = "${local.name}-analysis"
  visibility_timeout_seconds        = 6 * var.process_timeout_seconds
  message_retention_seconds         = 345600 # 4 days
  kms_master_key_id                 = aws_kms_key.main.arn
  kms_data_key_reuse_period_seconds = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.analysis_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only the analysis queue may use the DLQ.
resource "aws_sqs_queue_redrive_allow_policy" "analysis_dlq" {
  queue_url = aws_sqs_queue.analysis_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.analysis.arn]
  })
}

data "aws_iam_policy_document" "analysis_queue" {
  statement {
    sid       = "AllowUploadsBucketEvents"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.analysis.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.uploads.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "analysis" {
  queue_url = aws_sqs_queue.analysis.id
  policy    = data.aws_iam_policy_document.analysis_queue.json
}
