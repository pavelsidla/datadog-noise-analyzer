# AGENTS.md — Datadog Alert Noise Analyzer

## What You Are Building

A script that queries the Datadog API for alert history, identifies noisy/dead/misconfigured monitors in make-infra, and generates:
1. A human-readable report with Claude's analysis
2. Optionally: a Terraform PR with suggested threshold changes

**Problem:** `make-infra/datadog/monitoring/` manages 65+ Datadog monitors per zone. Over time, monitors become noisy (fire constantly without action taken), dead (never fire — possibly misconfigured or measuring the wrong thing), or their thresholds drift from reality. Alert Sheriff fatigue is real.

**This is different from the CSV idea "Create skills for managing Datadog Monitors"** — that idea is about creating/managing monitors via MCP. This tool is about auditing what already exists and generating data-driven improvement recommendations.

**Expected output:**
```
Datadog Alert Noise Analysis — Last 90 Days
==========================================

NOISY MONITORS (fire frequently, low resolution rate):
  ❌ [HIGH] rds_cpu_utilization_slave-eu1-production — Fired 847 times, avg resolution: 2min
     → Threshold may be too sensitive. Suggestion: raise critical from 80% → 90%
     → Terraform: modules/datadog_alerting/rds.tf:34

DEAD MONITORS (never fired in 90 days):
  ⚠️  k8s_pod_crash_looping_int — 0 alerts in 90 days
     → Either too high a threshold or environment is very stable. Consider removing.
     → Terraform: modules/datadog_alerting/kubernetes.tf:87

SLOW RESOLUTION (avg >4h):
  ⏰ disk_usage_slave-us1-production — Avg resolution: 6.2h
     → Consider adding a runbook link or adjusting severity

Summary: 3 noisy, 7 dead, 2 slow — estimated alert fatigue reduction: ~40%
```

---

## Repository: make-infra

**Clone location:** Likely at `~/projects/MAKE/make-infra` or similar.

### Key Files to Read in make-infra

1. **`datadog/monitoring/credentials.tf`** — How Datadog API credentials are fetched from AWS Secrets Manager.
   ```
   AWS Secrets Manager path: make/infra/shared/datadog
   Keys in the secret: api_key, app_key
   Region: eu-west-1 (backend from providers.tf)
   ```

2. **`datadog/monitoring/providers.tf`** — Provider versions and backend configuration.
   - Datadog provider: `3.66.0`
   - AWS provider: `5.90.0`
   - Terraform backend: `tfstate.infrastructure.eu-west-1.int.s3`

3. **`datadog/monitoring/monitoring.tf`** — Module instantiations per environment. Each block calls `modules/datadog/zone-monitoring` with a `zone_map` variable.

4. **`modules/datadog_alerting/rds.tf`** — Example monitor definition. Structure:
   ```hcl
   resource "datadog_monitor" "rds_cpu" {
     for_each = local.zone_map

     name    = "RDS CPU — ${each.key}"
     type    = "metric alert"
     query   = "avg(last_5m):avg:aws.rds.cpuutilization{...} > ${var.rds_cpu_critical}"

     thresholds = {
       critical          = var.rds_cpu_critical    # e.g. 80
       critical_recovery = var.rds_cpu_recovery    # e.g. 70
       warning           = var.rds_cpu_warning     # e.g. 60
     }

     notify_no_data    = false
     notify_infra_warning  = "..."  # Slack/PD routing
     notify_infra_critical = "..."
   }
   ```

5. **`modules/datadog_alerting/`** — List ALL `.tf` files here to see every monitor category:
   - `rds.tf` — RDS database monitors
   - `kubernetes.tf` — K8s cluster monitors
   - `elasticsearch.tf` — Search monitors
   - `redis.tf` — Cache monitors
   - etc.

6. **`modules/make_zones/variables.tf`** — Shows all zone variables including Datadog threshold variables.

---

## Datadog API Usage

### Authentication
```python
from datadog_api_client import ApiClient, Configuration

# Get credentials from AWS Secrets Manager at runtime
import boto3

def get_datadog_credentials() -> tuple[str, str]:
    client = boto3.client('secretsmanager', region_name='eu-west-1')
    secret = client.get_secret_value(SecretId='make/infra/shared/datadog')
    data = json.loads(secret['SecretString'])
    return data['api_key'], data['app_key']

api_key, app_key = get_datadog_credentials()
config = Configuration()
config.api_key['apiKeyAuth'] = api_key
config.api_key['appKeyAuth'] = app_key
```

### Key API Endpoints to Use

```python
from datadog_api_client.v1.api.monitors_api import MonitorsApi
from datadog_api_client.v1.api.events_api import EventsApi

# List all monitors
with ApiClient(config) as api_client:
    monitors_api = MonitorsApi(api_client)
    monitors = monitors_api.list_monitors(
        tags="terraform:true",  # if Terraform-managed monitors have this tag
        page_size=100
    )

# Get monitor alert history (events)
from datadog_api_client.v1.api.events_api import EventsApi
events_api = EventsApi(api_client)

# Last 90 days
end = int(time.time())
start = end - (90 * 24 * 3600)

events = events_api.list_events(
    start=start,
    end=end,
    sources="monitor",
    tags=f"monitor_id:{monitor_id}"
)
```

### Alternative: Datadog v2 API (preferred for newer features)
```python
from datadog_api_client.v2.api.metrics_api import MetricsApi
```

---

## Algorithm

```python
def analyze_monitors(monitors: list, days: int = 90) -> AnalysisResult:

    results = []

    for monitor in monitors:
        monitor_id = monitor.id
        monitor_name = monitor.name

        # Get alert history
        alerts = get_alert_events(monitor_id, days)

        # Calculate metrics
        alert_count = len([e for e in alerts if e.alert_type == "error"])
        recovery_count = len([e for e in alerts if e.alert_type == "success"])

        if alert_count == 0:
            # Dead monitor
            results.append(MonitorResult(monitor_id, "dead", alert_count=0))

        elif alert_count > NOISY_THRESHOLD:  # e.g. > 100 alerts in 90 days
            # Calculate average resolution time
            avg_resolution = calculate_avg_resolution_time(alerts)
            results.append(MonitorResult(monitor_id, "noisy",
                                          alert_count=alert_count,
                                          avg_resolution=avg_resolution))

        elif calculate_avg_resolution_time(alerts) > SLOW_THRESHOLD:  # e.g. > 4 hours
            results.append(MonitorResult(monitor_id, "slow", ...))

    return AnalysisResult(results)
```

---

## Claude Integration

Send the analysis results to Claude for human-readable recommendations:

```python
import anthropic

def generate_recommendations(analysis: AnalysisResult, terraform_context: str) -> str:
    client = anthropic.Anthropic()

    prompt = f"""
You are a Site Reliability Engineer analyzing Datadog alert quality.

Here is the alert analysis for the last 90 days:
{analysis.to_json()}

Here is the Terraform code that defines these monitors:
{terraform_context}

For each problematic monitor, provide:
1. A clear explanation of WHY this is a problem
2. A specific recommendation (threshold change, query change, or remove)
3. The exact Terraform file and variable to change

Format the output as actionable SRE recommendations.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text
```

---

## Environment Variables / Prerequisites

```bash
# AWS credentials (to access Secrets Manager)
AWS_PROFILE=<infra-profile>    # or use role assumption
# OR
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# Or if running in GitHub Actions with OIDC:
# The existing make-infra workflows use OIDC — check .github/workflows/ for the pattern

ANTHROPIC_API_KEY=<key>        # For Claude recommendations
```

---

## Testing

```bash
cd /Users/p.sidla/Documents/hackathon-implementations/03-datadog-noise-analyzer

pip install -r requirements.txt

# Test with real Datadog API (requires AWS credentials for secrets)
python noise_analyzer.py --days 90 --output report.md

# Test in dry-run mode (reads monitors but doesn't generate TF changes)
python noise_analyzer.py --days 90 --dry-run

# Test with a specific monitor name pattern
python noise_analyzer.py --days 90 --filter "rds_*"

# Generate Terraform diff suggestions
python noise_analyzer.py --days 90 --generate-tf-suggestions --tf-repo ~/projects/MAKE/make-infra
```

---

## Caveats & Edge Cases

1. **Datadog API rate limits** — List monitors and events APIs have rate limits. Use pagination and add small delays between requests. The `datadog-api-client` SDK handles retry logic.

2. **Monitor names may not map directly to Terraform resource names** — The Datadog monitor `name` field is human-readable. To map a monitor back to its Terraform source, you may need to look for tags like `terraform:true` and `managed_by:terraform`, or match by name pattern against the Terraform files.

3. **Zone-specific monitors** — Each zone has its own monitors (due to `for_each = local.zone_map`). The same Terraform resource generates monitors for every zone (eu1-production, us1-production, etc.). Group by Terraform resource name when reporting.

4. **Alert vs No-data alerts** — The events API includes both alert events and no-data events. Distinguish between them. A "dead" monitor (never fired) is different from one that fires no-data alerts.

5. **AWS credentials** — In the hackathon, you may not want to touch Secrets Manager. Alternative: accept `DD_API_KEY` and `DD_APP_KEY` as environment variables directly, which is the Datadog-standard way.

6. **Terraform recommendation scope** — Keep Terraform PR suggestions conservative: only recommend threshold changes, not query changes. Query changes are more risky.

---

## Optional: Terraform PR Generation

If you want to go further and generate actual Terraform diffs:

```python
def suggest_threshold_change(monitor: MonitorResult, tf_file: str) -> str:
    """
    Given a noisy monitor, suggest a threshold increase.
    Returns a git diff-formatted suggestion.
    """
    # Parse the relevant variable from the Terraform file
    # Suggest a +10% or +20% threshold increase
    # Format as a readable diff
    ...
```

This is complex — keep it optional for the hackathon. The human-readable report is already very valuable.

---

## Success Criteria

1. Script connects to Datadog API successfully (with real or mock credentials)
2. Correctly identifies at least one noisy monitor (fire count > threshold)
3. Correctly identifies at least one dead monitor (0 alerts in 90 days)
4. Claude generates readable, actionable recommendations
5. Output is formatted as a readable Markdown report
