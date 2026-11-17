"""Task 1 - Clean the metrics (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 1)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import OUT_DIR, TIMEZONE


def clean_metrics(raw: pd.DataFrame, out_dir: Path = OUT_DIR) -> tuple[pd.DataFrame, dict]:
    """Clean the raw metric exports and write out/metrics_clean.csv.

    Input: the table of loaders.load_metrics_raw() (source, timestamp as text, service, p95_latency_ms,
    error_rate_pct, requests_per_min).

    Returns the clean table (timestamp as timezone-aware Europe/Berlin, service, p95_latency_ms, error_rate_pct,
    requests_per_min) and a cleaning log with the keys rows_in, utc_converted, duplicates_removed,
    zero_latency_set_missing and rows_out.
    """
    raise NotImplementedError("Task 1 - see .kiro/specs/opspilot-data/requirements.md, Requirement 1")
