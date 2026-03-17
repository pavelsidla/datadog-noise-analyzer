"""
AWS Lambda entry point for the Datadog Noise Analyzer.

Triggered by EventBridge (weekly cron). Runs the full monitor analysis
and publishes custom metrics to Datadog.

Environment variables:
  DD_API_KEY           Datadog API key (OR pulled from Secrets Manager)
  DD_APP_KEY           Datadog Application key (OR pulled from Secrets Manager)
  ANALYSIS_DAYS        Days of history to analyze (default: 90)
  MAX_MONITORS         Max monitors per run (default: 200)
  MONITOR_ENVS         Comma-separated env tag values to filter monitors (default: production,production-pi)
  NOISY_THRESHOLD      Alert count threshold for noisy classification (default: 50)
  SLOW_RESOLUTION_HOURS  MTTR threshold in hours for slow classification (default: 4)
  DRY_RUN              Set to "true" to use mock data (default: false)
"""
import json
import os
import sys

# Adjust path so noise_analyzer.py (co-packaged in Lambda zip) is importable
sys.path.insert(0, os.path.dirname(__file__))

from noise_analyzer import (
    AnalysisResult,
    MonitorStats,
    get_api_config,
    get_datadog_credentials,
    get_mock_monitors,
    format_report,
    list_all_monitors,
    run_analysis,
)
from metrics_publisher import publish_metrics


def lambda_handler(event: dict, context) -> dict:
    """Main Lambda entry point."""
    dry_run = event.get("dry_run", os.environ.get("DRY_RUN", "false").lower() == "true")
    days = int(event.get("days", os.environ.get("ANALYSIS_DAYS", "90")))
    max_monitors = int(event.get("max_monitors", os.environ.get("MAX_MONITORS", "200")))
    monitor_envs_raw = os.environ.get("MONITOR_ENVS", "production,production-pi")
    env_filter = [e.strip() for e in monitor_envs_raw.split(",") if e.strip()]

    print(f"Starting noise analysis: days={days}, max_monitors={max_monitors}, dry_run={dry_run}, env_filter={env_filter}")

    if dry_run:
        print("DRY RUN: Using mock monitor data")
        monitors = get_mock_monitors()
        result = AnalysisResult(
            period_days=days,
            total_monitors=len(monitors),
            noisy=[MonitorStats(monitor=monitors[0], alert_count=847, avg_resolution_hours=0.5, category="noisy")],
            dead=[MonitorStats(monitor=monitors[1], alert_count=0, category="dead")],
            slow=[MonitorStats(monitor=monitors[2], alert_count=12, avg_resolution_hours=6.2, category="slow")],
        )
    else:
        api_key, app_key = get_datadog_credentials()
        config = get_api_config(api_key, app_key)

        print("Fetching monitors from Datadog API...")
        monitors = list_all_monitors(config, env_filter=env_filter)
        print(f"Found {len(monitors)} monitors to analyze")

        result = run_analysis(config, monitors, days, max_monitors=max_monitors)

    # Publish custom metrics to Datadog
    if not dry_run:
        try:
            publish_metrics(result)
            print("Published custom metrics to Datadog")
        except Exception as e:
            print(f"Warning: Failed to publish metrics: {e}")

    # Format report
    report = format_report(result)
    print(report)

    summary = {
        "period_days": days,
        "total_monitors": result.total_monitors,
        "noisy_count": len(result.noisy),
        "dead_count": len(result.dead),
        "slow_count": len(result.slow),
        "healthy_count": len(result.healthy),
        "health_score_pct": round(
            len(result.healthy) / result.total_monitors * 100 if result.total_monitors else 0, 1
        ),
    }
    print(f"Analysis complete: {json.dumps(summary)}")
    return summary


