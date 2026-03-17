output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.noise_analyzer.lambda_function_arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.noise_analyzer.lambda_function_name
}

output "lambda_role_arn" {
  description = "Lambda IAM role ARN"
  value       = module.noise_analyzer.lambda_role_arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name"
  value       = module.noise_analyzer.cloudwatch_log_group_name
}
