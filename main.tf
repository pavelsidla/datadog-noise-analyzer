module "noise_analyzer" {
  source = "./modules/noise-analyzer"

  function_name         = var.function_name
  datadog_secret_arn    = var.datadog_secret_arn
  report_s3_bucket      = var.report_s3_bucket
  schedule_expression   = var.schedule_expression
  analysis_days         = var.analysis_days
  max_monitors          = var.max_monitors
  noisy_threshold       = var.noisy_threshold
  slow_resolution_hours = var.slow_resolution_hours
  log_retention_days    = var.log_retention_days
  dry_run               = var.dry_run
  tags                  = var.tags
}
