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

variable "monitor_envs" {
  description = "List of Datadog environment tag values to analyze. Monitors must have at least one matching env:<value> tag. Configurable so environments can be added/removed without code changes."
  type        = list(string)
  default     = ["production", "production-pi"]
}

variable "vpc_subnet_ids" {
  description = "List of VPC subnet IDs for Lambda VPC deployment. Follow the same pattern as make-infra/modules/datadog_lambda."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "List of security group IDs for Lambda VPC deployment."
  type        = list(string)
  default     = []
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for automatic runs. Set to empty string to disable. Default: every Monday at 08:30 UTC (before oncall rota handover at 09:00)."
  type        = string
  default     = "cron(30 8 ? * MON *)"
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
