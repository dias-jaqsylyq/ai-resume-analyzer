variable "region" {
  description = "AWS region for the project"
  type        = string
  default     = "us-east-1"
}

variable "upload_retention_days" {
  description = "Days before an uploaded CV is deleted from the uploads bucket"
  type        = number
  default     = 7
}

variable "uploads_prefix" {
  description = "Key prefix for CV uploads; only objects under it are sent to the analysis queue"
  type        = string
  default     = "uploads/"
}

variable "process_timeout_seconds" {
  description = "Planned timeout of the process-analysis Lambda; the queue visibility timeout is 6x this (AWS guidance)"
  type        = number
  default     = 120
}

variable "max_receive_count" {
  description = "Delivery attempts before a message moves to the DLQ"
  type        = number
  default     = 3
}

variable "bedrock_mode" {
  description = "process-analysis model call: mock (deterministic, no Bedrock) or live (Amazon Nova via Converse)"
  type        = string
  default     = "mock"

  validation {
    condition     = contains(["mock", "live"], var.bedrock_mode)
    error_message = "bedrock_mode must be \"mock\" or \"live\"."
  }
}

variable "bedrock_model_id" {
  description = "Amazon Nova model used in live mode"
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for Lambda log groups"
  type        = number
  default     = 14
}
