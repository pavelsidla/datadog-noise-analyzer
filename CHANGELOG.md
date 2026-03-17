# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial Lambda-based architecture with EventBridge daily trigger
- Custom Datadog metrics: `monitor_analyzer.*` for noise score, alert count, MTTR, dead detection
- Terraform module (`modules/noise-analyzer`) with IAM, Lambda, EventBridge resources
- Datadog dashboard in Terraform (`dashboard/dashboard.tf`)
- Concurrent monitor analysis with `ThreadPoolExecutor` (8 workers)
- S3 report archiving (Markdown + JSON + AI recommendations)
- Lambda build script (`scripts/build_lambda.sh`)
- Simple and complete Terraform examples
- Pre-commit hooks for Terraform formatting and Python linting
