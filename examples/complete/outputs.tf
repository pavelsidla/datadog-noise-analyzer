output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.noise_analyzer.lambda_function_arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.noise_analyzer.lambda_function_name
}

output "report_bucket_name" {
  description = "S3 bucket for archived reports"
  value       = aws_s3_bucket.reports.id
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group"
  value       = module.noise_analyzer.cloudwatch_log_group_name
}
