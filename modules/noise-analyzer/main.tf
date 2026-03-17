locals {
  lambda_zip        = "${path.module}/../../src/lambda.zip"
  source_code_hash  = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null
}

# ── Lambda Function ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "noise_analyzer" {
  function_name = var.function_name
  role          = aws_iam_role.noise_analyzer.arn
  handler       = "lambda_handler.lambda_handler"
  runtime       = "python3.12"

  filename         = local.lambda_zip
  source_code_hash = local.source_code_hash

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory_mb

  environment {
    variables = merge(
      {
        ANALYSIS_DAYS    = tostring(var.analysis_days)
        MAX_MONITORS     = tostring(var.max_monitors)
        DRY_RUN          = tostring(var.dry_run)
      },
      var.report_s3_bucket != "" ? { REPORT_S3_BUCKET = var.report_s3_bucket } : {}
    )
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.noise_analyzer]
}

# ── IAM ──────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "noise_analyzer" {
  name = "${var.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "noise_analyzer" {
  name = "${var.function_name}-policy"
  role = aws_iam_role.noise_analyzer.id
  policy = templatefile("${path.module}/policy.tmpl", {
    secrets_arn   = var.datadog_secret_arn
    s3_bucket_arn = var.report_s3_bucket != "" ? "arn:aws:s3:::${var.report_s3_bucket}" : ""
    has_s3_bucket = var.report_s3_bucket != ""
  })
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.noise_analyzer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── CloudWatch Logs ───────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "noise_analyzer" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ── EventBridge Scheduled Trigger ────────────────────────────────────────────

resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.schedule_expression != "" ? 1 : 0

  name                = "${var.function_name}-schedule"
  description         = "Triggers the Datadog noise analyzer on a schedule"
  schedule_expression = var.schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "schedule" {
  count = var.schedule_expression != "" ? 1 : 0

  rule  = aws_cloudwatch_event_rule.schedule[0].name
  arn   = aws_lambda_function.noise_analyzer.arn
  input = jsonencode({ source = "eventbridge-schedule" })
}

resource "aws_lambda_permission" "eventbridge" {
  count = var.schedule_expression != "" ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.noise_analyzer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
