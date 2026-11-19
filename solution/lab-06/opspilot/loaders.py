"""Read the mock exports from data/. Ready to use - you do not need to change this file."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA_DIR, TIMEZONE

METRIC_EXPORTS = ("metrics_export_1.csv", "metrics_export_2.csv")


def load_metrics_raw(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Both Grafana metric exports, unchanged, in one table.

    Columns: source, timestamp (raw text, exactly as exported), service, p95_latency_ms, error_rate_pct,
    requests_per_min.
    """
    frames = []
    for name in METRIC_EXPORTS:
        df = pd.read_csv(data_dir / "grafana" / name, dtype={"timestamp": str, "service": str})
        df.insert(0, "source", name)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _to_local(values: pd.Series) -> pd.Series:
    """ISO timestamps with an offset (e.g. +01:00) as timezone-aware Europe/Berlin values."""
    return pd.to_datetime(values, utc=True).dt.tz_convert(TIMEZONE)


def load_tickets(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """ITSM customer tickets - contains personal data. created_at is timezone-aware."""
    df = pd.read_csv(data_dir / "itsm" / "tickets.csv", dtype=str)
    df["created_at"] = _to_local(df["created_at"])
    return df


def load_changes(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """ITSM changes and deployments. started_at and finished_at are timezone-aware (finished_at may be empty)."""
    df = pd.read_csv(data_dir / "itsm" / "changes.csv", dtype=str)
    for col in ("started_at", "finished_at"):
        df[col] = _to_local(df[col])
    return df


def load_load_baseline(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Average requests per minute per service, weekday (0 = Monday) and hour, measured last week."""
    return pd.read_csv(data_dir / "grafana" / "load_baseline_last_week.csv")


def load_slo(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """SLO per service: p95 threshold, target, window and the bad minutes already used before today."""
    return pd.read_csv(data_dir / "grafana" / "slo_budget.csv")
