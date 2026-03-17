"""
AWS Lambda entry point for the Datadog Noise Analyzer.

Triggered by EventBridge (daily cron). Runs the full monitor analysis
and publishes custom metrics to Datadog. Archives report to S3.

Environment variables:
  DD_API_KEY           Datadog API key (OR pulled from Secrets Manager)
  DD_APP_KEY           Datadog Application key (OR pulled from Secrets Manager)
  ANTHROPIC_API_KEY    For AI recommendations
  ANALYSIS_DAYS        Days of history to analyze (default: 90)
  MAX_MONITORS         Max monitors per run (default: 200)
  REPORT_S3_BUCKET     S3 bucket for archiving reports (optional)
  DRY_RUN              Set to "true" to use mock data (default: false)
"""
import json
import os
import sys
from datetime import datetime, timezone

# Adjust path so noise_analyzer.py (co-packaged in Lambda zip) is importable
sys.path.insert(0, os.path.dirname(__file__))

from noise_analyzer import (
    AnalysisResult,
    MonitorStats,
    generate_ai_report,
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
    s3_bucket = os.environ.get("REPORT_S3_BUCKET", "")

    print(f"Starting noise analysis: days={days}, max_monitors={max_monitors}, dry_run={dry_run}")

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
        monitors = list_all_monitors(config)
        print(f"Found {len(monitors)} monitors to analyze")

        result = run_analysis(config, monitors, days, max_monitors=max_monitors)

    # Generate AI recommendations
    print("Generating AI recommendations...")
    result.ai_report = generate_ai_report(result)

    # Publish custom metrics to Datadog
    if not dry_run:
        try:
            publish_metrics(result)
            print("Published custom metrics to Datadog")
        except Exception as e:
            print(f"Warning: Failed to publish metrics: {e}")

    # Format and archive report
    report = format_report(result)
    if s3_bucket:
        _archive_to_s3(s3_bucket, result, report)

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


def _archive_to_s3(bucket: str, result: AnalysisResult, report: str) -> None:
    """Archive markdown report and raw stats JSON to S3."""
    import boto3

    s3 = boto3.client("s3")
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    objects_to_put = {
        f"noise-analyzer/{date_prefix}/report.md": (report.encode(), "text/markdown"),
        f"noise-analyzer/{date_prefix}/stats.json": (
            json.dumps(_build_stats_dict(result, date_prefix), indent=2).encode(),
            "application/json",
        ),
    }
    if result.ai_report:
        objects_to_put[f"noise-analyzer/{date_prefix}/ai-recommendations.md"] = (
            result.ai_report.encode(),
            "text/markdown",
        )

    for key, (body, content_type) in objects_to_put.items():
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

    print(f"Archived report to s3://{bucket}/noise-analyzer/{date_prefix}/")


def _build_stats_dict(result: AnalysisResult, date: str) -> dict:
    return {
        "date": date,
        "period_days": result.period_days,
        "total_monitors": result.total_monitors,
        "noisy": [
            {
                "name": s.monitor.name,
                "id": s.monitor.id,
                "alert_count": s.alert_count,
                "avg_resolution_hours": round(s.avg_resolution_hours, 2),
            }
            for s in result.noisy
        ],
        "dead": [{"name": s.monitor.name, "id": s.monitor.id} for s in result.dead],
        "slow": [
            {
                "name": s.monitor.name,
                "id": s.monitor.id,
                "avg_resolution_hours": round(s.avg_resolution_hours, 2),
                "alert_count": s.alert_count,
            }
            for s in result.slow
        ],
    }
