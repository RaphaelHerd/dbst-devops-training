"""Task 1 - Clean the metrics (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 1)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import OUT_DIR, TIMEZONE


def parse_timestamps(raw: pd.Series) -> pd.Series:
    """Raw export timestamps as timezone-aware Europe/Berlin values.

    Values ending with Z are UTC and are converted. Values without an offset are local time.
    """
    is_utc = raw.str.endswith("Z")
    utc_part = pd.to_datetime(raw[is_utc], utc=True).dt.tz_convert(TIMEZONE).dt.as_unit("ns")
    local_part = pd.to_datetime(raw[~is_utc]).dt.tz_localize(TIMEZONE).dt.as_unit("ns")
    return pd.concat([utc_part, local_part]).sort_index()


def clean_metrics(raw: pd.DataFrame, out_dir: Path = OUT_DIR) -> tuple[pd.DataFrame, dict]:
    """Clean the raw metric exports and write out/metrics_clean.csv.

    Returns the clean table (timestamp, service, p95_latency_ms, error_rate_pct, requests_per_min)
    and a cleaning log with the counts of every fix.
    """
    df = raw.copy()
    log = {"rows_in": len(df), "utc_converted": int(df["timestamp"].str.endswith("Z").sum())}

    df["timestamp"] = parse_timestamps(df["timestamp"])

    before = len(df)
    df = df.drop_duplicates(subset=["service", "timestamp"], keep="first")
    log["duplicates_removed"] = before - len(df)

    zeros = df["p95_latency_ms"] == 0                  # a latency of 0 ms is a scrape gap, not a measurement
    log["zero_latency_set_missing"] = int(zeros.sum())
    df.loc[zeros, "p95_latency_ms"] = np.nan           # error rate and requests: 0 is a real value - keep it

    df = (df.drop(columns="source")
            .sort_values(["service", "timestamp"])
            .reset_index(drop=True))
    log["rows_out"] = len(df)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "metrics_clean.csv", index=False)
    return df, log
