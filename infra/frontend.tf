# Frontend hosting (RA-19): the Next.js static export lives in a private S3 bucket and is
# served only through CloudFront (Origin Access Control). The deploy job in ci.yml syncs
# frontend/out/ to the bucket, writes config.json from this stack's outputs and invalidates.

locals {
  web_bucket_name = "${local.name}-web-${local.account_id}"

  # The API and the uploads bucket accept browser calls from the CloudFront site
  # (plus var.allowed_origins, e.g. localhost for development).
  allowed_origins = concat(var.allowed_origins, ["https://${aws_cloudfront_distribution.web.domain_name}"])

  # The browser talks only to: this site, the HTTP API, Cognito (SRP sign-in) and the uploads
  # bucket (pre-signed POST). Wildcard execute-api avoids a cycle (the API's CORS needs this
  # distribution's domain). Next.js static export inlines small scripts, hence 'unsafe-inline'.
  web_csp = join("; ", [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    join(" ", [
      "connect-src 'self'",
      "https://*.execute-api.${var.region}.amazonaws.com",
      "https://cognito-idp.${var.region}.amazonaws.com",
      "https://${local.uploads_bucket_name}.s3.${var.region}.amazonaws.com",
      "https://s3.${var.region}.amazonaws.com",
    ]),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ])
}

# --- Bucket (private; only CloudFront can read) -------------------------------------------

resource "aws_s3_bucket" "web" {
  bucket        = local.web_bucket_name
  force_destroy = true # build output only; re-created by the next deploy
}

resource "aws_s3_bucket_ownership_controls" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3, not the project KMS key: the bucket holds only public JS/CSS/HTML (no personal data),
# and SSE-KMS behind CloudFront would add a KMS request per cache miss plus a key-policy grant
# to CloudFront. Still one customer managed key in the project (see docs/decisions.md).
resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "web_bucket" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.web.arn, "${aws_s3_bucket.web.arn}/*"]

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

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.web]
}

# --- CloudFront ---------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${local.name}-web"
  description                       = "CloudFront access to the frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 behind OAC has no index documents: map /analysis/ and /analysis to /analysis/index.html.
resource "aws_cloudfront_function" "web_index" {
  name    = "${local.name}-web-index"
  runtime = "cloudfront-js-2.0"
  comment = "Serve index.html for folder URLs of the static export"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
      } else if (uri.split('/').pop().indexOf('.') === -1) {
        request.uri = uri + '/index.html';
      }
      return request;
    }
  EOT
}

resource "aws_cloudfront_response_headers_policy" "web" {
  name    = "${local.name}-web-security"
  comment = "Security headers for the dashboard"

  security_headers_config {
    content_security_policy {
      content_security_policy = local.web_csp
      override                = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }
  }
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  comment             = "${local.name} dashboard"
  default_root_object = "index.html"
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100" # North America + Europe edges only: cheapest

  origin {
    origin_id                = "web-s3"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  default_cache_behavior {
    target_origin_id           = "web-s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.web.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.web_index.arn
    }
  }

  # Without s3:ListBucket, S3 answers 403 for a missing key; show the export's 404 page.
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
