terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }
  }

  # Remote state in the bucket created by infra/bootstrap, with S3 native locking.
  # The bucket name is account-specific, so it is passed at init time:
  #   terraform init -backend-config="bucket=$TF_STATE_BUCKET"
  backend "s3" {
    key          = "main/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
