provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "ai-resume-analyzer"
      ManagedBy = "terraform"
      Stack     = "main"
    }
  }
}
