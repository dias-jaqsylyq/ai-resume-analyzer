# One execution role per Lambda, least privilege. Each function gets only the permissions its
# code uses; Guardrails (RA-11) adds bedrock:ApplyGuardrail later.

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.functions

  name               = each.value
  description        = "Execution role for Lambda ${each.value}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

locals {
  # KMS is used only indirectly, through these services (kms:ViaService).
  kms_via = {
    s3       = "s3.${var.region}.amazonaws.com"
    sqs      = "sqs.${var.region}.amazonaws.com"
    dynamodb = "dynamodb.${var.region}.amazonaws.com"
    textract = "textract.${var.region}.amazonaws.com" # async Textract reads the SSE-KMS upload
  }

  log_group_arn = {
    for k, name in local.functions :
    k => "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${name}:*"
  }
}

# --- create-analysis: writes the PENDING item and signs the pre-signed PUT URL -------------
data "aws_iam_policy_document" "create_analysis" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.log_group_arn.create_analysis]
  }

  statement {
    sid       = "PutAnalysis"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.analyses.arn]
  }

  # A pre-signed PUT is executed with the signer's permissions.
  statement {
    sid       = "SignUpload"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/${var.uploads_prefix}*"]
  }

  statement {
    sid       = "UseKey"
    actions   = ["kms:GenerateDataKey", "kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.main.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.kms_via.s3, local.kms_via.dynamodb]
    }
  }
}

# --- process-analysis: SQS consumer; reads the CV, writes result + cache --------------------
data "aws_iam_policy_document" "process_analysis" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.log_group_arn.process_analysis]
  }

  statement {
    sid       = "ConsumeQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.analysis.arn]
  }

  statement {
    sid       = "ReadUpload"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/${var.uploads_prefix}*"]
  }

  # Textract actions do not support resource-level permissions.
  statement {
    sid       = "Textract"
    actions   = ["textract:StartDocumentTextDetection", "textract:GetDocumentTextDetection"]
    resources = ["*"]
  }

  # Converse is authorized by bedrock:InvokeModel; only the configured Nova model.
  statement {
    sid       = "InvokeNova"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"]
  }

  statement {
    sid       = "UpdateAnalysis"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.analyses.arn]
  }

  statement {
    sid       = "Cache"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.cache.arn]
  }

  statement {
    sid       = "UseKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:Encrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.main.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.kms_via.s3, local.kms_via.sqs, local.kms_via.dynamodb, local.kms_via.textract]
    }
  }
}

# --- read-analyses: API reads of a user's analyses ------------------------------------------
data "aws_iam_policy_document" "read_analyses" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.log_group_arn.read_analyses]
  }

  statement {
    sid       = "ReadAnalyses"
    actions   = ["dynamodb:Query", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.analyses.arn]
  }

  statement {
    sid       = "UseKey"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.main.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = [local.kms_via.dynamodb]
    }
  }
}

locals {
  lambda_policies = {
    create_analysis  = data.aws_iam_policy_document.create_analysis.json
    process_analysis = data.aws_iam_policy_document.process_analysis.json
    read_analyses    = data.aws_iam_policy_document.read_analyses.json
  }
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.lambda_policies

  name   = "least-privilege"
  role   = aws_iam_role.lambda[each.key].id
  policy = each.value
}
