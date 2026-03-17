output "lambda_function_arn" {
  description = "ARN of the noise analyzer Lambda function"
  value       = aws_lambda_function.noise_analyzer.arn
}

output "lambda_function_name" {
  description = "Name of the noise analyzer Lambda function"
  value       = aws_lambda_function.noise_analyzer.function_name
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution IAM role"
  value       = aws_iam_role.noise_analyzer.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for Lambda execution logs"
  value       = aws_cloudwatch_log_group.noise_analyzer.name
}

output "cloudwatch_log_group_arn" {
  description = "CloudWatch log group ARN"
  value       = aws_cloudwatch_log_group.noise_analyzer.arn
}

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge schedule rule (null if schedule_expression is empty)"
  value       = var.schedule_expression != "" ? aws_cloudwatch_event_rule.schedule[0].arn : null
}
