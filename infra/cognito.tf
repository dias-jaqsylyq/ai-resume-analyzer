# Cognito user pool for sign-in. API Gateway verifies its JWTs (api.tf); the user's `sub`
# claim is the partition key of their analyses (USER#<sub>) and part of the upload key.

resource "aws_cognito_user_pool" "main" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE" # the stack must be destroyable (demo, then destroy)

  admin_create_user_config {
    allow_admin_create_user_only = !var.allow_self_signup
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 3
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# Public client for the static Next.js app: no secret (it cannot be kept in a browser).
resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false
  # SRP for the web app; USER_PASSWORD_AUTH lets the owner get a token from CloudShell for a
  # smoke test (`aws cognito-idp initiate-auth`), still over TLS only.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
