module "noise_analyzer" {
  source = "../../"

  function_name         = "datadog-noise-analyzer-prod"
  datadog_secret_arn    = data.aws_secretsmanager_secret.datadog.arn
  report_s3_bucket      = aws_s3_bucket.reports.id
  schedule_expression   = "cron(0 6 * * ? *)"
  analysis_days         = 90
  max_monitors          = 300
  noisy_threshold       = 50
  slow_resolution_hours = 4
  log_retention_days    = 90

  tags = {
    Environment = "production"
    Team        = "sre"
    Project     = "noise-analyzer"
  }
}

# ── Data sources ─────────────────────────────────────────────────────────────

data "aws_secretsmanager_secret" "datadog" {
  name = "make/infra/shared/datadog"
}

# ── S3 report archive ─────────────────────────────────────────────────────────

resource "aws_s3_bucket" "reports" {
  bucket = "make-noise-analyzer-reports"

  tags = {
    Environment = "production"
    Project     = "noise-analyzer"
  }
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "expire-old-reports"
    status = "Enabled"

    expiration {
      days = 365
    }
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
