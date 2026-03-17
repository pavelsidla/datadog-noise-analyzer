# datadog-noise-analyzer

AWS Lambda + Terraform module that audits Datadog monitor quality and surfaces a live dashboard of noisy, dead, and slow-resolving monitors.

```
EventBridge (daily)
       │
       ▼
  Lambda (Python 3.12)
  ├── Query all Datadog monitors
  ├── Fetch 90d alert/recovery event history
  ├── Classify: noisy / dead / slow / healthy
  ├── Compute MTTR per monitor
  ├── Generate Claude AI recommendations
  ├── Publish custom metrics → Datadog
  └── Archive report → S3
                │
                ▼
        Datadog Dashboard
        custom.monitor.*
```

## Problem

Datadog monitors in `make-infra` accumulate technical debt:
- **Noisy** (>50 alerts/90d): cause alert fatigue, engineers stop responding
- **Dead** (0 alerts/90d): waste money, give false confidence
- **Slow to resolve** (avg MTTR >4h): no runbooks, unclear escalation

This tool runs daily and populates a Datadog dashboard with ranked, actionable data.

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
export DD_API_KEY=xxx DD_APP_KEY=yyy ANTHROPIC_API_KEY=zzz

# Dry run with mock data
python noise_analyzer.py --dry-run

# Real analysis
python noise_analyzer.py --days 90 --output report.md
```

### Deploy as Lambda

```bash
# 1. Build Lambda zip
bash scripts/build_lambda.sh

# 2. Apply Terraform
terraform init
terraform apply -var="datadog_secret_arn=arn:aws:secretsmanager:eu-west-1:ACCOUNT:secret:make/infra/shared/datadog"
```

### Deploy with Terraform module

```hcl
module "noise_analyzer" {
  source = "path/to/03-datadog-noise-analyzer"

  datadog_secret_arn = "arn:aws:secretsmanager:eu-west-1:ACCOUNT:secret:make/infra/shared/datadog"
  report_s3_bucket   = "my-reports-bucket"

  tags = {
    Team    = "sre"
    Project = "noise-analyzer"
  }
}
```

## Custom Metrics Published

All metrics are posted daily after each Lambda run.

### Per-monitor (tagged: `monitor_id`, `monitor_name`, `monitor_type`, `category`)

| Metric | Type | Description |
|--------|------|-------------|
| `custom.monitor.alert_count_90d` | GAUGE | Total alerts in analysis period |
| `custom.monitor.avg_resolution_hours` | GAUGE | Average MTTR in hours |
| `custom.monitor.is_dead` | GAUGE | `1` if zero alerts/no_data |
| `custom.monitor.noise_score` | GAUGE | 0-100 composite health score |

### Summary (tagged: `service:noise-analyzer`)

| Metric | Description |
|--------|-------------|
| `custom.monitor.estate_health_score` | % of healthy monitors |
| `custom.monitor.noisy_count` | Count of noisy monitors |
| `custom.monitor.dead_count` | Count of dead monitors |
| `custom.monitor.slow_count` | Count of slow monitors |
| `custom.monitor.total_analyzed` | Total monitors analyzed |

**Cost note**: ~800 custom metric timeseries/day for 200 monitors. Check your Datadog account's included custom metric quota.

## Monitor Categories

| Category | Condition |
|----------|-----------|
| `noisy` | `alert_count > 50` |
| `dead` | `alert_count == 0 AND no_data_count == 0` |
| `slow` | `avg_resolution_hours > 4 AND alert_count > 0` |
| `healthy` | Everything else |

Thresholds are configurable via Terraform variables (`noisy_threshold`, `slow_resolution_hours`).

## Project Structure

```
├── noise_analyzer.py          Core analysis logic (also works as CLI)
├── src/
│   ├── lambda_handler.py      Lambda entry point
│   ├── metrics_publisher.py   Datadog v2 MetricsAPI
│   └── requirements.txt
├── modules/noise-analyzer/    Terraform module (Lambda + IAM + EventBridge)
├── dashboard/dashboard.tf     Datadog dashboard (8 widgets)
├── examples/
│   ├── simple/                Minimal usage
│   └── complete/              Full production setup with S3 + lifecycle
├── scripts/build_lambda.sh    Lambda zip builder
└── .github/workflows/         CI/CD (pre-commit + semantic release)
```

## Task Split

### Engineer A — Infrastructure & Terraform
- [ ] Terraform module (`modules/noise-analyzer/`)
- [ ] Root module wiring (`main.tf`, `variables.tf`, `outputs.tf`)
- [ ] Dashboard (`dashboard/dashboard.tf`)
- [ ] Examples (`examples/simple/`, `examples/complete/`)
- [ ] CI/CD workflows (`.github/workflows/`)
- [ ] `versions.tf` provider constraints

### Engineer B — Python Lambda
- [ ] `src/lambda_handler.py` — Lambda entry point
- [ ] `src/metrics_publisher.py` — Datadog v2 MetricsAPI
- [ ] `noise_analyzer.py` — Add concurrent fetching with `ThreadPoolExecutor`
- [ ] S3 archiving in lambda_handler
- [ ] `scripts/build_lambda.sh` — packaging
- [ ] Update `AGENTS.md` with new architecture

## Brainstorming Questions

### Architecture
- Should the Lambda be triggered on-demand (API Gateway) in addition to the daily cron?
- VPC-deployed Lambda or public? Any Datadog API access restrictions from Make's network?
- Should we vendor the Lambda zip in the repo (like the forwarder module) or always build in CI?

### Metrics & Dashboard
- What custom metric quota does the Make Datadog account have? (~800 series/day)
- Convention for metric namespace: `custom.monitor.*` or `make.monitor.*`?
- Do we want per-monitor trend timeseries (requires multiple runs), or just latest-state snapshots?
- Should the dashboard live in `make-infra` Terraform or in this standalone repo?

### Thresholds & Logic
- Is 50 alerts/90d the right noisy threshold? Should it be configurable per team tag?
- Should dead monitors trigger a PR suggestion to remove the Terraform resource?
- Zone-aware analysis? (Some monitors intentionally fire only in specific zones)
- Should Claude recommendations be sent as Datadog Events or Notebook entries?

### Operational
- Which AWS account and region? Same as make-infra (eu-west-1)?
- Shared Datadog API key (service account) or team-specific?
- Alert on `custom.monitor.estate_health_score < 70`? Who gets paged?
- S3 report retention: 30 / 90 / 365 days?

### Future Features
- Auto-generate Terraform PRs to fix noisy monitors (the `--generate-tf-suggestions` stub)
- Slack notification with top 5 noisy + top 5 dead after each run
- Per-team attribution via Datadog monitor tags
- Multi-account / multi-org support

## Prerequisites

- Python 3.12+
- Terraform >= 1.5
- AWS CLI configured with access to `make/infra/shared/datadog` Secrets Manager secret
- Datadog API key + App key
- Anthropic API key (optional, for AI recommendations)

## Notes