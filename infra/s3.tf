# Uploads bucket: CVs arrive here via pre-signed PUT, are read once by the pipeline and expire.

resource "aws_s3_bucket" "uploads" {
  bucket = local.uploads_bucket_name
  # Only short-lived CV copies live here; lets the stack be destroyed and recreated from zero.
  force_destroy = true
}

resource "aws_s3_bucket_ownership_controls" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    # S3 Bucket Key: S3 reuses a bucket-level data key, cutting KMS requests (and cost).
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire-uploads"
    status = "Enabled"
    filter {}

    expiration {
      days = var.upload_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "uploads_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.uploads.arn, "${aws_s3_bucket.uploads.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  policy = data.aws_iam_policy_document.uploads_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.uploads]
}

# New CV under uploads/ -> message on the analysis queue.
# Note: S3 also sends one "s3:TestEvent" message when this is created; the consumer must skip it.
resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  queue {
    queue_arn     = aws_sqs_queue.analysis.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = var.uploads_prefix
  }

  depends_on = [aws_sqs_queue_policy.analysis]
}
