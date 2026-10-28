output "account_id" {
  description = "AWS account the stack is deployed to (confirms the OIDC role works)"
  value       = data.aws_caller_identity.current.account_id
}
