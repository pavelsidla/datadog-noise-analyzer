module "noise_analyzer" {
  source = "../../"

  # Required: ARN of the secret containing {"api_key": "...", "app_key": "..."}
  datadog_secret_arn = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:make/infra/shared/datadog"

  tags = {
    Environment = "production"
    Team        = "sre"
    Project     = "noise-analyzer"
  }
}
