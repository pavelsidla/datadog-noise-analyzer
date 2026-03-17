# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- `analysis_days` production config set to **30 days** (was 90 in plan, aligned with test results)
- `noisy_threshold` production config set to **15 alerts/30d** (was 50 — calibrated lower for Make's monitor estate)
- Removed stale `report_s3_bucket` and `max_monitors` vars from root `main.tf` (never accepted by module)

## [1.0.0] — 2026-03-17

### Added
- Initial Lambda-based architecture with EventBridge weekly trigger (Mon 08:30 UTC)
- Custom Datadog metrics: `monitor_analyzer.*` — noise score, alert count, MTTR, dead detection
- `env:production` + `env:production-pi` tags forwarded from monitor tags onto every metric series
- Terraform module (`modules/noise-analyzer`) with IAM, Lambda, EventBridge, CloudWatch log group
- Datadog dashboard in Terraform (`dashboard/dashboard.tf`) with 8 widgets + one-click monitor deep links
- Concurrent monitor analysis with `ThreadPoolExecutor` (8 workers) — 477 monitors in ~2 min
- Lambda build script (`scripts/build_lambda.sh`)
- Simple and complete Terraform usage examples
- End-to-end tested with real DD credentials: 477 monitors, 1,913 metrics published

### Deployed to make-infra
- `modules/noise-analyzer` — Terraform module (PR: integromat/make-infra#3581)
- `accounts/int/eu-west-1/make-secrets/.../noise_analyzer.tf` — cross-account secret with `datadog-noise-analyzer-role` access
- `accounts/int/eu-west-1/infrastructure/noise-analyzer/` — VPC-deployed Lambda, private subnets, NAT egress
