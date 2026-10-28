variable "region" {
  description = "AWS region for the project"
  type        = string
  default     = "us-east-1"
}

variable "github_owner" {
  description = "GitHub user or organization that owns the repository"
  type        = string
  default     = "dias-jaqsylyq"
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "ai-resume-analyzer"
}

variable "github_oidc_sub_prefix" {
  description = "OIDC subject prefix GitHub issues for this repo (immutable format with numeric owner/repo IDs)"
  type        = string
  default     = "repo:dias-jaqsylyq@167603429/ai-resume-analyzer@1437005887"
}
