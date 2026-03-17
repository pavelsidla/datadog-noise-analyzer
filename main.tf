module "noise_analyzer" {
  source = "./modules/noise-analyzer"

  function_name         = var.function_name
  datadog_secret_arn    = var.datadog_secret_arn
  schedule_expression   = var.schedule_expression
  analysis_days         = var.analysis_days
  noisy_threshold       = var.noisy_threshold
  slow_resolution_hours = var.slow_resolution_hours
  log_retention_days    = var.log_retention_days
  dry_run               = var.dry_run
  tags                  = var.tags
}
