locals {
  lambda_zip        = "${path.module}/lambda.zip"
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
    variables = {
      ANALYSIS_DAYS         = tostring(var.analysis_days)
      DRY_RUN               = tostring(var.dry_run)
      MONITOR_ENVS          = join(",", var.monitor_envs)
      NOISY_THRESHOLD       = tostring(var.noisy_threshold)
      SLOW_RESOLUTION_HOURS = tostring(var.slow_resolution_hours)
    }
  }

  dynamic "vpc_config" {
    for_each = length(var.vpc_subnet_ids) > 0 ? [1] : []
    content {
      subnet_ids         = var.vpc_subnet_ids
      security_group_ids = var.security_group_ids
    }
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
    secrets_arn = var.datadog_secret_arn
  })
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.noise_analyzer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc_execution" {
  count      = length(var.vpc_subnet_ids) > 0 ? 1 : 0
  role       = aws_iam_role.noise_analyzer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
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
