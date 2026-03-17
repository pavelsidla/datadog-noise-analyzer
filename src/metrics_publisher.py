"""
Publishes computed monitor health metrics to Datadog via v2 MetricsAPI.

Custom metrics posted per Lambda run:

  Per-monitor (tagged: monitor_id, monitor_name, monitor_type, category):
    custom.monitor.alert_count_90d        — alert count over the analysis period
    custom.monitor.avg_resolution_hours   — average MTTR in hours
    custom.monitor.is_dead                — 1 if zero alerts/no_data, 0 otherwise
    custom.monitor.noise_score            — 0-100 composite health score

  Summary (tagged: service:noise-analyzer):
    custom.monitor.estate_health_score    — % of healthy monitors
    custom.monitor.noisy_count            — count of noisy monitors
    custom.monitor.dead_count             — count of dead monitors
    custom.monitor.slow_count             — count of slow monitors
    custom.monitor.total_analyzed         — total monitors analyzed
"""
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noise_analyzer import AnalysisResult, MonitorStats

_NOISY_THRESHOLD = 50
_SLOW_RESOLUTION_HOURS = 4
_METRIC_CHUNK_SIZE = 500  # Max series per submit_metrics call


def _compute_noise_score(alert_count: int, avg_resolution_hours: float, category: str) -> float:
    """
    0-100 composite health score. Higher = healthier.
    Dead monitors are always 0 (distinct problem from noisy).
    """
    if category == "dead":
        return 0.0
    score = 100.0
    score -= min(50.0, (alert_count / _NOISY_THRESHOLD) * 50.0)
    score -= min(25.0, (avg_resolution_hours / _SLOW_RESOLUTION_HOURS) * 25.0)
    return max(0.0, score)


def publish_metrics(result: "AnalysisResult") -> None:
    """Build and submit all custom metrics to Datadog in batches."""
    try:
        from datadog_api_client import ApiClient, Configuration
        from datadog_api_client.v2.api.metrics_api import MetricsApi
        from datadog_api_client.v2.model.metric_intake_type import MetricIntakeType
        from datadog_api_client.v2.model.metric_payload import MetricPayload
        from datadog_api_client.v2.model.metric_point import MetricPoint
        from datadog_api_client.v2.model.metric_series import MetricSeries
    except ImportError as e:
        raise ImportError(f"datadog-api-client not installed: {e}") from e

    config = Configuration()
    config.api_key["apiKeyAuth"] = os.environ.get("DD_API_KEY", "")
    config.api_key["appKeyAuth"] = os.environ.get("DD_APP_KEY", "")

    now = int(time.time())
    all_series: list = []

    # ── Per-monitor metrics ──────────────────────────────────────────────────
    all_stats = result.noisy + result.dead + result.slow + result.healthy
    for stats in all_stats:
        # Datadog tag values have a 200-char limit; truncate name to be safe
        monitor_tags = [
            f"monitor_id:{stats.monitor.id}",
            f"monitor_name:{stats.monitor.name[:100]}",
            f"monitor_type:{stats.monitor.type}",
            f"category:{stats.category}",
        ]
        noise_score = _compute_noise_score(
            stats.alert_count, stats.avg_resolution_hours, stats.category
        )

        per_monitor = [
            ("custom.monitor.alert_count_90d", float(stats.alert_count)),
            ("custom.monitor.avg_resolution_hours", float(stats.avg_resolution_hours)),
            ("custom.monitor.is_dead", 1.0 if stats.category == "dead" else 0.0),
            ("custom.monitor.noise_score", noise_score),
        ]
        for metric_name, value in per_monitor:
            all_series.append(
                MetricSeries(
                    metric=metric_name,
                    type=MetricIntakeType.GAUGE,
                    points=[MetricPoint(timestamp=now, value=value)],
                    tags=monitor_tags,
                )
            )

    # ── Summary metrics ──────────────────────────────────────────────────────
    total = result.total_monitors
    healthy_count = len(result.healthy)
    health_score = (healthy_count / total * 100.0) if total > 0 else 0.0

    summary_metrics = [
        ("custom.monitor.estate_health_score", health_score),
        ("custom.monitor.noisy_count", float(len(result.noisy))),
        ("custom.monitor.dead_count", float(len(result.dead))),
        ("custom.monitor.slow_count", float(len(result.slow))),
        ("custom.monitor.total_analyzed", float(total)),
    ]
    for metric_name, value in summary_metrics:
        all_series.append(
            MetricSeries(
                metric=metric_name,
                type=MetricIntakeType.GAUGE,
                points=[MetricPoint(timestamp=now, value=value)],
                tags=["service:noise-analyzer"],
            )
        )

    # ── Submit in chunks ─────────────────────────────────────────────────────
    with ApiClient(config) as api_client:
        api = MetricsApi(api_client)
        for i in range(0, len(all_series), _METRIC_CHUNK_SIZE):
            chunk = all_series[i : i + _METRIC_CHUNK_SIZE]
            api.submit_metrics(body=MetricPayload(series=chunk))
            print(f"  Submitted {len(chunk)} metric series ({i + len(chunk)}/{len(all_series)} total)")
