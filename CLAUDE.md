# CLAUDE.md — Datadog Noise Analyzer

This file contains binding instructions for Claude Code and any AI agent working in this repository.

---

## CRITICAL: No Direct Pushes to Main

**Every change — no matter how small — MUST go through a Pull Request.**

This is enforced because this repository is shared between multiple engineers working in parallel.
Direct commits to `main` are not allowed and will conflict with others' work.

### Required workflow

```
1. Create a new branch from main
   git checkout main && git pull origin main
   git checkout -b <type>/<short-description>

2. Make your changes

3. Commit with a clear message
   git add <specific files>
   git commit -m "feat: describe what changed and why"

4. Push the branch
   git push -u origin <branch-name>

5. Open a PR using gh
   gh pr create --title "..." --body "..."

6. Do NOT merge your own PR without review (unless explicitly told to)
```

### Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<desc>` | `feat/add-slack-notifications` |
| Bug fix | `fix/<desc>` | `fix/mttr-calculation-edge-case` |
| Infra/Terraform | `infra/<desc>` | `infra/add-eventbridge-schedule` |
| Docs | `docs/<desc>` | `docs/update-readme-env-filter` |
| Refactor | `refactor/<desc>` | `refactor/extract-filter-logic` |

---

## Project Overview

Weekly Lambda that audits Datadog monitor quality at Make — filters to `env:production` (420 monitors) +
`env:production-pi` (57 monitors) = **477 monitors** analyzed every Monday at 06:00 UTC.

**Confluence page (source of truth for design decisions):**
https://make.atlassian.net/wiki/x/GgCHqg

### What it does

1. **FETCH + FILTER** — List all 814 monitors, keep only `env:production` + `env:production-pi` = 477
2. **FETCH HISTORY** — Alert + recovery events per monitor, last 30 days (8 threads in parallel)
3. **CLASSIFY** — Noisy (>15 alerts/30d), Dead (0 alerts), Slow (avg MTTR >4h), Healthy
4. **COMPUTE MTTR** — Pair alert→recovery events per monitor (native Datadog cannot do this)
5. **PUBLISH** — Post custom metrics to Datadog via v2 MetricsAPI

### Schedule

Weekly cron: `cron(30 8 ? * MON *)` (every Monday 08:30 UTC — before oncall rota handover at 09:00)

### Custom metrics produced

- `monitor_analyzer.alert_count` — per monitor (30d window)
- `monitor_analyzer.avg_resolution_hours` — per monitor
- `monitor_analyzer.is_dead` — per monitor
- `monitor_analyzer.noise_score` — per monitor
- `monitor_analyzer.estate_health_score` — summary
- `monitor_analyzer.noisy_count` — summary
- `monitor_analyzer.dead_count` — summary
- `monitor_analyzer.slow_count` — summary
- `monitor_analyzer.total_analyzed` — summary

**Total: 1,913 timeseries per run · ~7,652/month**

## Resolved decisions (from Confluence comments — March 2026)

| Topic | Decision |
|-------|---------|
| Schedule | Every Monday 08:30 UTC — `cron(30 8 ? * MON *)` — before oncall rota handover at 09:00 |
| Environment filter | `env:production` + `env:production-pi` only. Configurable via `monitor_envs` Terraform variable |
| API Gateway trigger | No — weekly cron only |
| VPC deployment | Yes — follow `make-infra/modules/datadog_lambda` pattern. Use `vpc_subnet_ids` + `security_group_ids` vars |
| Lambda zip | Vendored at `modules/noise-analyzer/lambda.zip` for first iteration. Build with `scripts/build_lambda.sh` |
| Dashboard location | make-infra Terraform repo (not this repo). `dashboard/dashboard.tf` here is a reference template |
| Metric namespace | `monitor_analyzer.*` confirmed |
| Tag convention | `env:production` and `env:production-pi` |
| Analysis window | 30 days — configurable via `analysis_days` Terraform variable |
| Noisy threshold | 15 alerts/30d — configurable via `noisy_threshold` Terraform variable |
| Dead monitors | Flag only — no auto-PR in first iteration |
| Claude AI recommendations | NOT in first iteration — metrics and dashboard only |
| S3 archiving | NOT in first iteration — metrics and dashboard only |
| Health score alerting | No paging — dashboard visibility only |
| AWS account | Infrastructure account |
| Datadog credentials | Shared service account via Secrets Manager — same pattern as `make-infra/modules/datadog_lambda` |
| Release env | Not included |
| Per-monitor trend | Yes — visible in dashboard after 4+ weekly runs |

---

## File Structure

```
noise_analyzer.py          Core analysis logic — CLI + Lambda-importable
src/
  lambda_handler.py        Lambda entry point + S3 archiving
  metrics_publisher.py     Datadog v2 MetricsAPI submission
  requirements.txt
modules/noise-analyzer/    Terraform module (Lambda + IAM + EventBridge)
dashboard/dashboard.tf     Datadog dashboard (8 widgets)
examples/simple/           Minimal Terraform usage example
examples/complete/         Full Terraform usage example
scripts/build_lambda.sh    Builds src/lambda.zip for deployment
```

---

## Local Development

```bash
pip install -r requirements.txt
export DD_API_KEY=xxx DD_APP_KEY=yyy

# Dry run (no metrics published)
python noise_analyzer.py --dry-run --env production --env production-pi

# Full run
python noise_analyzer.py --env production --env production-pi
```

## Deploy

```bash
bash scripts/build_lambda.sh

terraform init && terraform apply \
  -var="datadog_secret_arn=arn:aws:secretsmanager:eu-west-1:ACCOUNT:secret:make/infra/shared/datadog" \
  -var='monitor_envs=["production","production-pi"]' \
  -var='vpc_subnet_ids=["subnet-xxxx","subnet-yyyy"]' \
  -var='security_group_ids=["sg-xxxx"]'
```
