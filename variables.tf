variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "datadog-noise-analyzer"
}

variable "datadog_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Datadog API and App keys"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge schedule expression. Default: every Monday at 08:30 UTC (before oncall rota handover at 09:00)."
  type        = string
  default     = "cron(30 8 ? * MON *)"
}

variable "analysis_days" {
  description = "Days of monitor history to analyze"
  type        = number
  default     = 90
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

variable "monitor_envs" {
  description = "Datadog environment tag values to analyze (e.g. production, production-pi)"
  type        = list(string)
  default     = ["production", "production-pi"]
}

variable "vpc_subnet_ids" {
  description = "VPC subnet IDs for Lambda"
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security group IDs for Lambda VPC deployment"
  type        = list(string)
  default     = []
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
