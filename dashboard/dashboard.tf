# Datadog dashboard for noise analyzer custom metrics.
#
# Metrics are populated by the Lambda after each run.
# The dashboard will be empty until the Lambda runs at least once.
#
# Required provider: DataDog/datadog >= 3.0

resource "datadog_dashboard" "noise_analyzer" {
  title        = "Datadog Monitor Noise Analyzer"
  description  = "Monitor health estate — powered by the noise-analyzer Lambda. Refreshes daily."
  layout_type  = "ordered"
  reflow_type  = "fixed"

  # ── Row 1: Overview KPIs ───────────────────────────────────────────────────

  widget {
    group_definition {
      title            = "Estate Health Overview"
      layout_type      = "ordered"
      background_color = "blue"

      widget {
        query_value_definition {
          title       = "Total Monitors Analyzed"
          title_size  = "16"
          title_align = "left"
          autoscale   = true
          precision   = 0
          request {
            q          = "avg:custom.monitor.total_analyzed{*}"
            aggregator = "last"
          }
        }
      }

      widget {
        query_value_definition {
          title       = "Health Score"
          title_size  = "16"
          title_align = "left"
          autoscale   = true
          precision   = 1
          request {
            q          = "avg:custom.monitor.estate_health_score{*}"
            aggregator = "last"
            conditional_formats {
              comparator = ">="
              value      = 80
              palette    = "white_on_green"
            }
            conditional_formats {
              comparator = ">="
              value      = 60
              palette    = "white_on_yellow"
            }
            conditional_formats {
              comparator = "<"
              value      = 60
              palette    = "white_on_red"
            }
          }
        }
      }

      widget {
        query_value_definition {
          title       = "Noisy Monitors"
          title_size  = "16"
          title_align = "left"
          autoscale   = true
          precision   = 0
          request {
            q          = "avg:custom.monitor.noisy_count{*}"
            aggregator = "last"
            conditional_formats {
              comparator = ">"
              value      = 10
              palette    = "white_on_red"
            }
            conditional_formats {
              comparator = ">"
              value      = 5
              palette    = "white_on_yellow"
            }
          }
        }
      }

      widget {
        query_value_definition {
          title       = "Dead Monitors"
          title_size  = "16"
          title_align = "left"
          autoscale   = true
          precision   = 0
          request {
            q          = "avg:custom.monitor.dead_count{*}"
            aggregator = "last"
            conditional_formats {
              comparator = ">"
              value      = 20
              palette    = "white_on_yellow"
            }
          }
        }
      }

      widget {
        query_value_definition {
          title       = "Slow to Resolve"
          title_size  = "16"
          title_align = "left"
          autoscale   = true
          precision   = 0
          request {
            q          = "avg:custom.monitor.slow_count{*}"
            aggregator = "last"
            conditional_formats {
              comparator = ">"
              value      = 5
              palette    = "white_on_yellow"
            }
          }
        }
      }
    }
  }

  # ── Row 2: Top Noisy Monitors ─────────────────────────────────────────────

  widget {
    toplist_definition {
      title = "Top Noisy Monitors — Alert Count (90d)"
      request {
        q = "top(max:custom.monitor.alert_count_90d{*} by {monitor_name}, 20, 'max', 'desc')"
        conditional_formats {
          comparator = ">"
          value      = 100
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = ">="
          value      = 50
          palette    = "white_on_yellow"
        }
        conditional_formats {
          comparator = "<"
          value      = 50
          palette    = "white_on_green"
        }
      }
    }
  }

  # ── Row 3: Slowest MTTR ────────────────────────────────────────────────────

  widget {
    toplist_definition {
      title = "Slowest Resolving Monitors — Avg MTTR (hours)"
      request {
        q = "top(max:custom.monitor.avg_resolution_hours{category:slow} by {monitor_name}, 15, 'max', 'desc')"
        conditional_formats {
          comparator = ">"
          value      = 8
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = ">="
          value      = 4
          palette    = "white_on_yellow"
        }
      }
    }
  }

  # ── Row 4: Dead Monitors ───────────────────────────────────────────────────

  widget {
    toplist_definition {
      title = "Dead Monitors — Zero Alerts in 90d"
      request {
        q = "top(max:custom.monitor.is_dead{*} by {monitor_name,monitor_type}, 25, 'max', 'desc')"
        conditional_formats {
          comparator = ">"
          value      = 0
          palette    = "white_on_yellow"
        }
      }
    }
  }

  # ── Row 5: Noise Score Distribution ───────────────────────────────────────

  widget {
    toplist_definition {
      title = "Worst Noise Score (0 = worst, 100 = healthy)"
      request {
        q = "top(avg:custom.monitor.noise_score{*} by {monitor_name}, 20, 'min', 'asc')"
        conditional_formats {
          comparator = "<"
          value      = 30
          palette    = "white_on_red"
        }
        conditional_formats {
          comparator = "<"
          value      = 60
          palette    = "white_on_yellow"
        }
        conditional_formats {
          comparator = ">="
          value      = 60
          palette    = "white_on_green"
        }
      }
    }
  }

  # ── Row 6: Trend Over Time ─────────────────────────────────────────────────

  widget {
    timeseries_definition {
      title        = "Estate Health Trend"
      show_legend  = true
      legend_layout = "auto"

      request {
        q            = "avg:custom.monitor.estate_health_score{*}"
        display_type = "line"
        style {
          palette    = "green"
          line_type  = "solid"
          line_width = "thick"
        }
        metadata {
          expression = "avg:custom.monitor.estate_health_score{*}"
          alias_name = "Health Score %"
        }
      }

      request {
        q            = "avg:custom.monitor.noisy_count{*}"
        display_type = "bars"
        style {
          palette = "warm"
        }
        metadata {
          expression = "avg:custom.monitor.noisy_count{*}"
          alias_name = "Noisy"
        }
      }

      request {
        q            = "avg:custom.monitor.dead_count{*}"
        display_type = "bars"
        style {
          palette = "cool"
        }
        metadata {
          expression = "avg:custom.monitor.dead_count{*}"
          alias_name = "Dead"
        }
      }

      yaxis {
        min   = "0"
        max   = "auto"
        label = "Count / Score"
      }
    }
  }

  # ── Row 7: Live Monitor Events (native Datadog — no custom metric cost) ────

  widget {
    event_stream_definition {
      title          = "Recent Monitor Events (Live)"
      query          = "sources:monitor"
      event_size     = "s"
      tags_execution = "and"
    }
  }

  # ── Row 8: Current Monitor State Summary ──────────────────────────────────

  widget {
    monitor_summary_definition {
      title            = "Current Monitor States"
      monitor_query    = "tag:*"
      summary_type     = "monitors"
      sort             = "status,asc"
      display_format   = "counts_and_list"
      color_preference = "background"
      count            = 50
      start            = 0
    }
  }

  tags = ["team:sre", "project:noise-analyzer", "managed-by:terraform"]
}
