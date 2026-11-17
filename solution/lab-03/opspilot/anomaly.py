"""Anomaly detection on the p95 latency.

naive_detect() is ready and shows the naive approach. detect_events() is Task 3
(rules: .kiro/specs/opspilot-data/requirements.md, Requirement 3).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

METRIC = "p95_latency_ms"


@dataclass
class AnomalyEvent:
    """One anomaly event: consecutive anomalous minutes of one service."""

    service: str
    metric: str
    start: pd.Timestamp
    end: pd.Timestamp
    baseline_ms: float
    peak_ms: float
    minutes_since_deployment: float | None = None
    deployment_version: str | None = None


def naive_detect(raw: pd.DataFrame, service: str = "payment-api", window: int = 20,
                 threshold: float = 3.0) -> pd.DataFrame:
    """The naive approach: glue both exports together and compare each value with the last 20 values.

    Returns the flagged rows with the columns ts, p95_latency_ms and z.
    """
    df = raw[raw["service"] == service].copy()
    df["ts"] = pd.to_datetime(df["timestamp"].str.replace("Z", "", regex=False).str.replace("T", " ", regex=False))
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    values = df[METRIC]
    df["z"] = (values - values.rolling(window).mean()) / values.rolling(window).std()
    return df.loc[df["z"].abs() > threshold, ["ts", METRIC, "z"]].reset_index(drop=True)


def detect_events(df: pd.DataFrame, window: str = "30min", threshold: float = 3.0, min_minutes: int = 2,
                  min_periods: int = 20) -> list[AnomalyEvent]:
    """Robust anomaly detection on the clean metrics (Task 3, Requirement 3).

    Works on the output of clean_metrics() and, if present, uses the features of add_features()
    (minutes_since_deployment, last_deployment_version).
    """
    events: list[AnomalyEvent] = []
    for service, group in df.sort_values("timestamp").groupby("service", sort=True):
        g = group.set_index("timestamp")
        series = g[METRIC]
        # baseline = the previous 30 minutes, the current minute is NOT part of its own baseline
        rolling = series.rolling(window, closed="left", min_periods=min_periods)
        std = rolling.std().where(lambda s: s > 0)
        z = (series - rolling.mean()) / std
        flagged = z.abs() > threshold                      # missing values give NaN and are never flagged

        for run in _consecutive_runs(flagged[flagged].index):
            if len(run) < min_minutes:
                continue
            start, end = run[0], run[-1]
            before = series[(series.index >= start - pd.Timedelta(window)) & (series.index < start)]
            event = AnomalyEvent(
                service=service,
                metric=METRIC,
                start=start,
                end=end,
                baseline_ms=float(before.median()),
                peak_ms=float(series[start:end].max()),
            )
            if "minutes_since_deployment" in g.columns:
                value = g.loc[start, "minutes_since_deployment"]
                event.minutes_since_deployment = None if pd.isna(value) else float(value)
            if "last_deployment_version" in g.columns:
                value = g.loc[start, "last_deployment_version"]
                event.deployment_version = None if pd.isna(value) else str(value)
            events.append(event)
    return events


def _consecutive_runs(stamps: pd.DatetimeIndex) -> list[list[pd.Timestamp]]:
    """Split sorted timestamps into runs of consecutive minutes."""
    runs: list[list[pd.Timestamp]] = []
    for ts in stamps:
        if runs and ts - runs[-1][-1] == pd.Timedelta(minutes=1):
            runs[-1].append(ts)
        else:
            runs.append([ts])
    return runs
