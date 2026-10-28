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
