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
2. **FETCH HISTORY** — Alert + recovery events per monitor, last 90 days (8 threads in parallel)
3. **CLASSIFY** — Noisy (>50 alerts/90d), Dead (0 alerts), Slow (avg MTTR >4h), Healthy
4. **COMPUTE MTTR** — Pair alert→recovery events per monitor (native Datadog cannot do this)
5. **CLAUDE AI** — Generate actionable recommendations for noisy and slow monitors
6. **PUBLISH** — Post 1,913 custom metrics to Datadog via v2 MetricsAPI
7. **ARCHIVE** — Save report.md + stats.json + ai-recommendations.md to S3

### Schedule

Weekly cron: `0 6 ? * MON *` (every Monday 06:00 UTC)

### Custom metrics produced

- `custom.monitor.alert_count_90d` — per monitor
- `custom.monitor.avg_resolution_hours` — per monitor
- `custom.monitor.is_dead` — per monitor
- `custom.monitor.noise_score` — per monitor
- `custom.monitor.estate_health_score` — summary
- `custom.monitor.noisy_count` — summary
- `custom.monitor.dead_count` — summary
- `custom.monitor.slow_count` — summary
- `custom.monitor.total_analyzed` — summary

**Total: 1,913 timeseries per run · ~7,652/month**

### Key open decisions (confirm before implementing)

- Tag convention: `env:production` or `environment:production`? Confirm in Datadog.
- Metric namespace: `custom.monitor.*` or `make.monitor.*`?
- AWS account + region (assumed `eu-west-1`)
- S3 bucket name and retention policy

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
export DD_API_KEY=xxx DD_APP_KEY=yyy ANTHROPIC_API_KEY=zzz

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
  -var="schedule_expression=cron(0 6 ? * MON *)" \
  -var="monitor_envs=[\"production\",\"production-pi\"]"
```
