# DynamoDB tables (on-demand, encrypted with the project CMK). Data model: docs/02-architecture.md.

# analyses: pk = USER#<sub>, sk = ANALYSIS#<ulid>
resource "aws_dynamodb_table" "analyses" {
  name         = "${local.name}-analyses"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.main.arn
  }
}

# cache: pk = sha256(CV bytes + job description); items expire via TTL on expires_at (epoch seconds).
resource "aws_dynamodb_table" "cache" {
  name         = "${local.name}-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.main.arn
  }
}
