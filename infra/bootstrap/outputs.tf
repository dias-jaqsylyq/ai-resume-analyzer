output "role_arn" {
  description = "IAM role ARN for GitHub Actions (set as repo variable AWS_ROLE_ARN)"
  value       = aws_iam_role.github_actions.arn
}

output "state_bucket" {
  description = "S3 bucket for Terraform remote state (set as repo variable TF_STATE_BUCKET)"
  value       = aws_s3_bucket.tfstate.bucket
}

output "region" {
  description = "AWS region (set as repo variable AWS_REGION)"
  value       = var.region
}
