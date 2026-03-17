variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "datadog-noise-analyzer"
}

variable "datadog_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing Datadog API and App keys (JSON with 'api_key' and 'app_key' fields)"
  type        = string
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds. Allow at least 3s per monitor analyzed."
  type        = number
  default     = 600 # 10 minutes — sufficient for 200 monitors with concurrent fetching
}

variable "lambda_memory_mb" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 256
}

variable "analysis_days" {
  description = "Number of days of monitor event history to analyze"
  type        = number
  default     = 90
}

variable "max_monitors" {
  description = "Maximum number of monitors to analyze per run (controls cost and runtime)"
  type        = number
  default     = 200
}

variable "noisy_threshold" {
  description = "Alert count above which a monitor is classified as noisy"
  type        = number
  default     = 50
}

variable "slow_resolution_hours" {
  description = "Average resolution time (hours) above which a monitor is classified as slow"
  type        = number
  default     = 4
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for automatic runs. Set to empty string to disable. Default: daily at 06:00 UTC."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "report_s3_bucket" {
  description = "S3 bucket name for archiving Markdown reports and raw stats JSON. Leave empty to disable archiving."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "dry_run" {
  description = "Run in dry-run mode with mock data (useful for initial testing)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all AWS resources"
  type        = map(string)
  default     = {}
}
