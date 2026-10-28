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
