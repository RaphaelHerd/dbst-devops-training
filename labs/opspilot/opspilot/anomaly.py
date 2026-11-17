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
    """Robust anomaly detection on the clean metrics. Returns one AnomalyEvent per real anomaly.

    Input: the output of clean_metrics() or of add_features(). If the feature columns minutes_since_deployment
    and last_deployment_version are present, copy their values at the event start into the event.
    """
    raise NotImplementedError("Task 3 - see .kiro/specs/opspilot-data/requirements.md, Requirement 3")
