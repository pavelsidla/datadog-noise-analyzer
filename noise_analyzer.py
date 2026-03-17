#!/usr/bin/env python3
"""
Datadog Alert Noise Analyzer for make-infra monitors.

Queries Datadog API for the last N days of alert history,
identifies noisy / dead / slow-resolution monitors.

Usage:
  python noise_analyzer.py --days 90 --output report.md
  python noise_analyzer.py --days 90 --dry-run
  python noise_analyzer.py --days 30 --filter "rds_*"
  python noise_analyzer.py --days 90 --env production --env production-pi

Environment variables:
  DD_API_KEY       Datadog API key (OR use AWS Secrets Manager — see AGENTS.md)
  DD_APP_KEY       Datadog Application key
  AWS_PROFILE      If using Secrets Manager to get Datadog credentials
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────

@dataclass
class MonitorInfo:
    id: int
    name: str
    type: str
    query: str
    tags: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class MonitorStats:
    monitor: MonitorInfo
    alert_count: int = 0
    recovery_count: int = 0
    no_data_count: int = 0
    avg_resolution_hours: float = 0.0
    category: str = "healthy"   # noisy / dead / slow / healthy
    recommendation: str = ""


@dataclass
class AnalysisResult:
    period_days: int
    total_monitors: int
    noisy: list[MonitorStats] = field(default_factory=list)
    dead: list[MonitorStats] = field(default_factory=list)
    slow: list[MonitorStats] = field(default_factory=list)
    healthy: list[MonitorStats] = field(default_factory=list)
    ai_report: str = ""


# ─────────────────────────────────────────────
# Credentials
# ─────────────────────────────────────────────

def get_datadog_credentials() -> tuple[str, str]:
    """
    Get Datadog API and App keys.

    Priority:
    1. DD_API_KEY / DD_APP_KEY environment variables (simplest for hackathon)
    2. AWS Secrets Manager at make/infra/shared/datadog (production pattern)
    """
    api_key = os.environ.get("DD_API_KEY")
    app_key = os.environ.get("DD_APP_KEY")

    if api_key and app_key:
        return api_key, app_key

    # Try AWS Secrets Manager
    try:
        import boto3

        profile = os.environ.get("AWS_PROFILE")
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        client = session.client("secretsmanager", region_name="eu-west-1")

        print("Fetching Datadog credentials from AWS Secrets Manager...", file=sys.stderr)
        secret = client.get_secret_value(SecretId="make/infra/shared/datadog")
        data = json.loads(secret["SecretString"])
        return data["api_key"], data["app_key"]

    except Exception as e:
        print(f"Failed to get credentials from Secrets Manager: {e}", file=sys.stderr)
        print("Set DD_API_KEY and DD_APP_KEY environment variables.", file=sys.stderr)
        sys.exit(1)


# ─────────────────────────────────────────────
# Datadog API client
# ─────────────────────────────────────────────

def get_api_config(api_key: str, app_key: str):
    """Build Datadog API client configuration."""
    try:
        from datadog_api_client import Configuration
        config = Configuration()
        config.api_key["apiKeyAuth"] = api_key
        config.api_key["appKeyAuth"] = app_key
        return config
    except ImportError:
        print("Install datadog-api-client: pip install datadog-api-client", file=sys.stderr)
        sys.exit(1)


def list_all_monitors(config, env_filter: Optional[list[str]] = None, name_filter: Optional[str] = None) -> list[MonitorInfo]:
    """List all Datadog monitors (paginated)."""
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.monitors_api import MonitorsApi

    monitors = []

    with ApiClient(config) as api_client:
        api = MonitorsApi(api_client)
        page = 0

        while True:
            result = api.list_monitors(page=page, page_size=100)
            if not result:
                break

            for m in result:
                # Apply name filter if provided
                if name_filter:
                    import fnmatch
                    if not fnmatch.fnmatch(m.name.lower(), name_filter.lower()):
                        continue

                monitors.append(MonitorInfo(
                    id=m.id,
                    name=m.name,
                    type=m.type,
                    query=m.query if hasattr(m, "query") and m.query else "",
                    tags=list(m.tags) if m.tags else [],
                    message=m.message if hasattr(m, "message") and m.message else "",
                ))

            if len(result) < 100:
                break
            page += 1
            time.sleep(0.2)  # Respect rate limits

    if env_filter:
        monitors = [
            m for m in monitors
            if any(f"env:{e}" in m.tags for e in env_filter)
        ]

    return monitors


def get_monitor_events(config, monitor_id: int, days: int) -> list[dict]:
    """
    Get alert events for a specific monitor over the last N days.

    Returns list of event dicts with: alert_type, date_happened, monitor_id
    """
    from datadog_api_client import ApiClient
    from datadog_api_client.v1.api.events_api import EventsApi

    end = int(time.time())
    start = end - (days * 24 * 3600)

    try:
        with ApiClient(config) as api_client:
            api = EventsApi(api_client)
            result = api.list_events(
                start=start,
                end=end,
                sources="monitor",
                tags=f"monitor_id:{monitor_id}",
            )

            events = []
            if result and result.events:
                for event in result.events:
                    events.append({
                        "alert_type": getattr(event, "alert_type", "unknown"),
                        "date_happened": getattr(event, "date_happened", 0),
                        "title": getattr(event, "title", ""),
                    })
            return events

    except Exception as e:
        print(f"  Warning: Failed to get events for monitor {monitor_id}: {e}", file=sys.stderr)
        return []


# ─────────────────────────────────────────────
# Analysis logic
# ─────────────────────────────────────────────

# Thresholds — read from environment, overridable via Terraform variable
NOISY_THRESHOLD = int(os.environ.get("NOISY_THRESHOLD", "50"))
DEAD_THRESHOLD = 0
SLOW_RESOLUTION_HOURS = float(os.environ.get("SLOW_RESOLUTION_HOURS", "4"))


def calculate_avg_resolution_hours(events: list[dict]) -> float:
    """
    Calculate average time between an alert firing and its recovery.
    Returns hours.
    """
    alert_times = []
    recovery_times = []

    for event in sorted(events, key=lambda e: e.get("date_happened", 0)):
        alert_type = event.get("alert_type", "")
        timestamp = event.get("date_happened", 0)

        if alert_type in ("error", "triggered", "alert"):
            alert_times.append(timestamp)
        elif alert_type in ("success", "recovered", "recovery"):
            recovery_times.append(timestamp)

    if not alert_times or not recovery_times:
        return 0.0

    # Match alerts to recoveries naively (sequential matching)
    durations = []
    for alert_t in alert_times:
        # Find the first recovery after this alert
        recovery = next((r for r in recovery_times if r > alert_t), None)
        if recovery:
            durations.append((recovery - alert_t) / 3600)  # seconds to hours

    return sum(durations) / len(durations) if durations else 0.0


def analyze_monitor(config, monitor: MonitorInfo, days: int) -> MonitorStats:
    """Fetch events and categorize a single monitor."""
    print(f"  Analyzing: {monitor.name}...", file=sys.stderr)
    events = get_monitor_events(config, monitor.id, days)

    alert_count = sum(1 for e in events if e.get("alert_type") in ("error", "triggered", "alert"))
    recovery_count = sum(1 for e in events if e.get("alert_type") in ("success", "recovered", "recovery"))
    no_data_count = sum(1 for e in events if "no_data" in e.get("alert_type", ""))

    avg_resolution = calculate_avg_resolution_hours(events)

    stats = MonitorStats(
        monitor=monitor,
        alert_count=alert_count,
        recovery_count=recovery_count,
        no_data_count=no_data_count,
        avg_resolution_hours=avg_resolution,
    )

    # Categorize
    if alert_count == 0 and no_data_count == 0:
        stats.category = "dead"
    elif alert_count > NOISY_THRESHOLD:
        stats.category = "noisy"
    elif avg_resolution > SLOW_RESOLUTION_HOURS and alert_count > 0:
        stats.category = "slow"
    else:
        stats.category = "healthy"

    return stats


def run_analysis(
    config,
    monitors: list[MonitorInfo],
    days: int,
    max_monitors: int = 200,
    max_workers: int = 8,
) -> AnalysisResult:
    """
    Run analysis across all monitors concurrently.

    Uses ThreadPoolExecutor to fetch monitor events in parallel, reducing
    runtime from ~400s to ~50s for 200 monitors compared to sequential fetching.
    Each thread creates its own ApiClient, so there are no shared-state issues.
    """
    result = AnalysisResult(period_days=days, total_monitors=len(monitors))
    monitors_to_analyze = monitors[:max_monitors]
    total = len(monitors_to_analyze)

    all_stats: list[MonitorStats] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_monitor = {
            executor.submit(analyze_monitor, config, monitor, days): monitor
            for monitor in monitors_to_analyze
        }
        for future in as_completed(future_to_monitor):
            monitor = future_to_monitor[future]
            completed += 1
            try:
                stats = future.result()
                print(f"[{completed}/{total}] {monitor.name} → {stats.category}", file=sys.stderr)
                all_stats.append(stats)
            except Exception as e:
                print(f"[{completed}/{total}] Error analyzing {monitor.name}: {e}", file=sys.stderr)

    for stats in all_stats:
        if stats.category == "dead":
            result.dead.append(stats)
        elif stats.category == "noisy":
            result.noisy.append(stats)
        elif stats.category == "slow":
            result.slow.append(stats)
        else:
            result.healthy.append(stats)

    # Sort by severity
    result.noisy.sort(key=lambda s: s.alert_count, reverse=True)
    result.slow.sort(key=lambda s: s.avg_resolution_hours, reverse=True)

    return result


# ─────────────────────────────────────────────
# Claude recommendations
# ─────────────────────────────────────────────

def generate_ai_report(result: AnalysisResult, tf_repo_root: Optional[Path] = None) -> str:
    """Use Claude to generate actionable recommendations."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "(Claude recommendations skipped — set ANTHROPIC_API_KEY)"

    # Prepare summary for Claude
    noisy_summary = [
        {
            "name": s.monitor.name,
            "alert_count": s.alert_count,
            "avg_resolution_hours": round(s.avg_resolution_hours, 1),
            "query": s.monitor.query[:100],
        }
        for s in result.noisy[:10]  # Top 10 noisy
    ]

    dead_summary = [
        {"name": s.monitor.name, "type": s.monitor.type}
        for s in result.dead[:10]  # Top 10 dead
    ]

    slow_summary = [
        {
            "name": s.monitor.name,
            "avg_resolution_hours": round(s.avg_resolution_hours, 1),
            "alert_count": s.alert_count,
        }
        for s in result.slow[:5]
    ]

    prompt = f"""You are an SRE reviewing Datadog alert quality for a cloud infrastructure team.

Analysis period: {result.period_days} days
Total monitors analyzed: {result.total_monitors}

NOISY MONITORS (top 10, fired most frequently with unclear value):
{json.dumps(noisy_summary, indent=2)}

DEAD MONITORS (top 10, never fired in {result.period_days} days):
{json.dumps(dead_summary, indent=2)}

SLOW TO RESOLVE (avg resolution > {SLOW_RESOLUTION_HOURS}h):
{json.dumps(slow_summary, indent=2)}

For each category, provide:
1. The most impactful action to take (be specific)
2. For noisy monitors: suggest a threshold change (e.g. "raise critical from X% to Y%") or query fix
3. For dead monitors: suggest if they should be removed or if the query is likely wrong
4. For slow monitors: suggest adding runbook links or escalation paths

Format as a clean Markdown report with sections.
Be concise and actionable — this is for engineers, not management.
"""

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ─────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────

def format_report(result: AnalysisResult) -> str:
    """Format analysis as Markdown report."""
    lines = [
        "# Datadog Alert Noise Analysis",
        f"Period: last {result.period_days} days  |  "
        f"Total monitors: {result.total_monitors}  |  "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Summary",
        f"- ❌ Noisy monitors: {len(result.noisy)}",
        f"- 💀 Dead monitors: {len(result.dead)}",
        f"- ⏰ Slow to resolve: {len(result.slow)}",
        f"- ✅ Healthy: {len(result.healthy)}",
        "",
    ]

    if result.noisy:
        lines += [
            "## ❌ Noisy Monitors",
            "_(Fire frequently with low signal value)_",
            "",
            "| Monitor | Alerts | Avg Resolution | Query Excerpt |",
            "|---------|--------|----------------|---------------|",
        ]
        for s in result.noisy[:20]:
            query_short = s.monitor.query[:60].replace("|", "\\|") + "..."
            lines.append(
                f"| {s.monitor.name} | {s.alert_count} | {s.avg_resolution_hours:.1f}h | `{query_short}` |"
            )
        lines.append("")

    if result.dead:
        lines += [
            "## 💀 Dead Monitors",
            "_(Never fired in the analysis period — may be misconfigured or measuring wrong metric)_",
            "",
        ]
        for s in result.dead[:20]:
            lines.append(f"- `{s.monitor.name}` (type: {s.monitor.type})")
        lines.append("")

    if result.slow:
        lines += [
            "## ⏰ Slow Resolution",
            f"_(Average resolution time > {SLOW_RESOLUTION_HOURS}h)_",
            "",
            "| Monitor | Avg Resolution | Alert Count |",
            "|---------|----------------|-------------|",
        ]
        for s in result.slow:
            lines.append(f"| {s.monitor.name} | {s.avg_resolution_hours:.1f}h | {s.alert_count} |")
        lines.append("")

    if result.ai_report:
        lines += [
            "## 🤖 AI Recommendations",
            "",
            result.ai_report,
            "",
        ]

    lines.append("---")
    lines.append("_Generated by noise-analyzer · make-infra hackathon tool_")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Mock data for testing without credentials
# ─────────────────────────────────────────────

def get_mock_monitors() -> list[MonitorInfo]:
    """Return fake monitors for testing without Datadog credentials."""
    return [
        MonitorInfo(id=1, name="rds_cpu_utilization_slave-eu1-production",
                    type="metric alert",
                    query="avg(last_5m):avg:aws.rds.cpuutilization{...} > 80"),
        MonitorInfo(id=2, name="k8s_pod_crash_looping_int",
                    type="metric alert",
                    query="max(last_5m):max:kubernetes.containers.restarts{...} > 5"),
        MonitorInfo(id=3, name="disk_usage_slave-us1-production",
                    type="metric alert",
                    query="avg(last_5m):avg:system.disk.in_use{...} > 0.9"),
    ]


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analyze Datadog alert noise")
    parser.add_argument("--days", type=int, default=90, help="Analysis period in days (default: 90)")
    parser.add_argument("--output", default="-", help="Output file path (default: stdout)")
    parser.add_argument("--dry-run", action="store_true", help="Use mock data, don't call Datadog API")
    parser.add_argument("--filter", help="Filter monitors by name pattern (e.g. 'rds_*')")
    parser.add_argument("--max-monitors", type=int, default=200, help="Max monitors to analyze")
    parser.add_argument("--env", action="append", dest="env_filter",
                        metavar="ENV", help="Filter to monitors with this env tag (can repeat). E.g. --env production --env production-pi")
    args = parser.parse_args()

    env_filter = args.env_filter  # list[str] | None

    if args.dry_run:
        print("DRY RUN: Using mock monitor data", file=sys.stderr)
        monitors = get_mock_monitors()
        result = AnalysisResult(
            period_days=args.days,
            total_monitors=len(monitors),
            noisy=[MonitorStats(monitor=monitors[0], alert_count=847, avg_resolution_hours=0.5, category="noisy")],
            dead=[MonitorStats(monitor=monitors[1], alert_count=0, category="dead")],
            slow=[MonitorStats(monitor=monitors[2], alert_count=12, avg_resolution_hours=6.2, category="slow")],
        )
    else:
        # Get real credentials
        api_key, app_key = get_datadog_credentials()
        config = get_api_config(api_key, app_key)

        print(f"Fetching monitors from Datadog API...", file=sys.stderr)
        monitors = list_all_monitors(config, env_filter=env_filter, name_filter=args.filter)
        print(f"Found {len(monitors)} monitors to analyze", file=sys.stderr)

        result = run_analysis(config, monitors, args.days, max_monitors=args.max_monitors)

    # Format report
    report = format_report(result)

    # Output
    if args.output == "-":
        print(report)
    else:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
