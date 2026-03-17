variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "datadog-noise-analyzer"
}

variable "datadog_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Datadog API and App keys"
  type        = string
}

variable "report_s3_bucket" {
  description = "S3 bucket for report archiving (empty = disabled)"
  type        = string
  default     = ""
}

variable "schedule_expression" {
  description = "EventBridge schedule expression (default: daily at 06:00 UTC)"
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "analysis_days" {
  description = "Days of monitor history to analyze"
  type        = number
  default     = 90
}

variable "max_monitors" {
  description = "Maximum monitors to analyze per run"
  type        = number
  default     = 200
}

variable "noisy_threshold" {
  description = "Alert count threshold for 'noisy' classification"
  type        = number
  default     = 50
}

variable "slow_resolution_hours" {
  description = "MTTR threshold (hours) for 'slow' classification"
  type        = number
  default     = 4
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "dry_run" {
  description = "Enable dry-run mode with mock data"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
