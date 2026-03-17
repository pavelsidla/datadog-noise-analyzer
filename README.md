# datadog-noise-analyzer

AWS Lambda + Terraform module that audits Datadog monitor quality and surfaces a live dashboard of noisy, dead, and slow-resolving monitors.

```
EventBridge (weekly: Mon 08:30 UTC)
       │
       ▼
  Lambda (Python 3.12, 256MB, 10min timeout)
  ├── Fetch all ~814 Datadog monitors
  ├── FILTER: env:production (420) + env:production-pi (57) = 477 monitors
  ├── GET /api/v1/monitor/{id}?group_states=all  ← per-group state (8 threads)
  ├── Classify: noisy / dead / slow / healthy
  ├── Compute MTTR per monitor (last_triggered_ts → last_resolved_ts pairs)
  └── Publish custom metrics → Datadog via v2 MetricsAPI
                │
                ▼
        Datadog Dashboard
        monitor_analyzer.*  (8 widgets, one-click monitor links)
```

## Problem

Datadog monitors in `make-infra` accumulate technical debt:
- **Noisy** (>15 alerts/30d): cause alert fatigue, engineers stop responding
- **Dead** (0 alerts/30d): waste money, give false confidence
- **Slow to resolve** (avg MTTR >4h): no runbooks, unclear escalation

This tool runs **every Monday at 08:30 UTC** (before oncall rota handover at 09:00) and populates a Datadog dashboard with ranked, actionable data.

## Why not native Datadog?

Native Datadog cannot:
- Compute MTTR (requires stateful alert→recovery event pairing)
- Detect dead monitors (absence of events is not a queryable metric value)
- Apply custom thresholds or composite noise scores

The Lambda layer solves this. Native Datadog widgets (event stream, monitor summary) are added alongside for real-time context at no extra cost.

## Usage

### Quick start (CLI, no AWS required)

```bash
pip install -r requirements.txt
export DD_API_KEY=xxx DD_APP_KEY=yyy

# Dry run with mock data
python noise_analyzer.py --dry-run --env production --env production-pi

# Real analysis (30d window, production envs)
python noise_analyzer.py --env production --env production-pi
```

### Deploy to make-infra (production)

The module lives in `make-infra/modules/noise-analyzer`. Deployment follows the bootstrap order below because the Lambda IAM role must exist before the secret's resource policy can reference it.

```
Step 1 — Deploy Lambda (creates IAM role: datadog-noise-analyzer-role)
  cd make-infra/accounts/int/eu-west-1/infrastructure/noise-analyzer
  terraform init && terraform apply

Step 2 — Deploy secret (grants datadog-noise-analyzer-role cross-account GetSecretValue)
  cd make-infra/accounts/int/eu-west-1/make-secrets/002_secrets/infra/infrastructure
  terraform init && terraform apply
  → Manually set secret value in AWS Console:
    { "api_key": "<DD_API_KEY>", "app_key": "<DD_APP_KEY>" }

Step 3 — Invoke (dry run first)
  aws lambda invoke --function-name datadog-noise-analyzer \
    --payload '{"dry_run": true}' \
    --profile make-infrastructure out.json && cat out.json
```

### Build Lambda zip

```bash
bash scripts/build_lambda.sh
# Outputs: modules/noise-analyzer/lambda.zip
```

## Custom Metrics Published

Weekly run produces **~1,913 timeseries** (~7,652/month). All metrics tagged with `env:production` / `env:production-pi` forwarded from the monitor's own tags.

### Per-monitor (tagged: `monitor_id`, `monitor_name`, `monitor_type`, `category`, `env`)

| Metric | Description |
|--------|-------------|
| `monitor_analyzer.alert_count` | Total group-triggers in the 30-day analysis period |
| `monitor_analyzer.avg_resolution_hours` | Average MTTR in hours |
| `monitor_analyzer.is_dead` | `1` if zero alerts and zero no_data groups |
| `monitor_analyzer.noise_score` | 0–100 composite health score |

### Summary (tagged: `service:noise-analyzer`)

| Metric | Description |
|--------|-------------|
| `monitor_analyzer.estate_health_score` | % of healthy monitors |
| `monitor_analyzer.noisy_count` | Count of noisy monitors |
| `monitor_analyzer.dead_count` | Count of dead monitors |
| `monitor_analyzer.slow_count` | Count of slow monitors |
| `monitor_analyzer.total_analyzed` | Total monitors analyzed |

## Monitor Categories

| Category | Condition |
|----------|-----------|
| `noisy` | `alert_count > 15` (configurable: `noisy_threshold`) |
| `dead` | `alert_count == 0 AND no_data_count == 0` |
| `slow` | `avg_resolution_hours > 4 AND alert_count > 0` (configurable: `slow_resolution_hours`) |
| `healthy` | Everything else |

## Infrastructure

| Resource | Details |
|----------|---------|
| AWS account | `make-infrastructure` (976645087541) |
| Secret account | `make-secrets` (381492280108) |
| Secret name | `make/infra/infrastructure/noise-analyzer` |
| Lambda role | `datadog-noise-analyzer-role` |
| Schedule | `cron(30 8 ? * MON *)` — Monday 08:30 UTC |
| VPC | Private subnets, NAT egress to Datadog API + Secrets Manager |

## Project Structure

```
├── noise_analyzer.py          Core analysis logic (CLI + Lambda-importable)
├── src/
│   ├── lambda_handler.py      Lambda entry point
│   ├── metrics_publisher.py   Datadog v2 MetricsAPI
│   └── requirements.txt
├── modules/noise-analyzer/    Terraform module (Lambda + IAM + EventBridge)
├── dashboard/dashboard.tf     Datadog dashboard reference template (deployed via make-infra)
├── examples/
│   ├── simple/                Minimal usage
│   └── complete/              Full Terraform usage example
├── scripts/build_lambda.sh    Lambda zip builder
└── .github/workflows/         CI/CD (semantic release)
```

## Verification

```bash
# Secret created in make-secrets account
aws secretsmanager describe-secret \
  --secret-id make/infra/infrastructure/noise-analyzer \
  --profile make-secrets

# Lambda deployed in infrastructure account
aws lambda get-function \
  --function-name datadog-noise-analyzer \
  --profile make-infrastructure

# Dry-run invoke
aws lambda invoke --function-name datadog-noise-analyzer \
  --payload '{"dry_run": true}' \
  --profile make-infrastructure out.json && cat out.json

# Metrics visible in Datadog within a few minutes after a real run
# Search: monitor_analyzer.* in Metrics Explorer
# CloudWatch logs: /aws/lambda/datadog-noise-analyzer
```

## Prerequisites

- Python 3.12+
- Terraform >= 1.5
- AWS profiles: `make-infrastructure` + `make-secrets`
- Datadog API key + App key (`monitors_read` scope only needed)
