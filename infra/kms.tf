# ONE customer managed key for the whole project (S3 uploads, SQS, DynamoDB).
# Each CMK costs $1/month, so there are no per-service keys (see docs/decisions.md).

data "aws_iam_policy_document" "kms" {
  # Standard default: the account (IAM policies) controls use of the key.
  statement {
    sid       = "EnableIamPolicies"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account_id}:root"]
    }
  }

  # S3 event notifications are delivered to a KMS-encrypted queue only if S3 can use the key.
  statement {
    sid       = "AllowS3EventsToEncryptedQueue"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.uploads_bucket_arn]
    }
  }
}

resource "aws_kms_key" "main" {
  description             = "${local.name}: encrypts CV uploads, queue messages and analysis results"
  enable_key_rotation     = true
  rotation_period_in_days = 365
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}
