"""Task 2 - Quality report and features (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 2)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import OUT_DIR, TIMEZONE

LOW, HIGH = 0.7, 1.3          # load_level thresholds: ratio to the same hour last week


def add_features(clean: pd.DataFrame, changes: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Add the columns hour, weekday, minutes_since_deployment, last_deployment_version and load_level."""
    df = clean.copy()
    df["timestamp"] = df["timestamp"].dt.as_unit("ns")
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.day_of_week          # 0 = Monday

    deployments = changes[(changes["type"] == "deployment") & changes["finished_at"].notna()]
    deployments = (deployments[["service", "finished_at", "version"]]
                   .rename(columns={"finished_at": "deployed_at", "version": "last_deployment_version"})
                   .assign(deployed_at=lambda d: d["deployed_at"].dt.as_unit("ns"))
                   .sort_values("deployed_at"))
    df = pd.merge_asof(df.sort_values("timestamp"), deployments, left_on="timestamp", right_on="deployed_at",
                       by="service", direction="backward")
    df["minutes_since_deployment"] = ((df["timestamp"] - df["deployed_at"]).dt.total_seconds() / 60).round()
    df = df.drop(columns="deployed_at")

    df = df.merge(baseline, on=["service", "weekday", "hour"], how="left")
    ratio = df["requests_per_min"] / df["avg_requests_per_min"]
    df["load_level"] = np.select([ratio.isna(), ratio < LOW, ratio > HIGH], ["unknown", "low", "high"],
                                 default="normal")
    df = df.drop(columns="avg_requests_per_min")
    return df.sort_values(["service", "timestamp"]).reset_index(drop=True)


def write_quality_report(raw: pd.DataFrame, clean: pd.DataFrame, log: dict, mask_counts: dict | None = None,
                         path: Path = OUT_DIR / "data_quality.md") -> Path:
    """Write the data-quality report as Markdown and return its path."""
    lines = ["# Data-Quality Report - opspilot data", "",
             f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
             "## Metric exports", "",
             "| Export | Rows | First timestamp (raw) | Last timestamp (raw) | Time format |",
             "|---|---:|---|---|---|"]
    for source, part in raw.groupby("source", sort=True):
        fmt = "UTC (ends with Z)" if part["timestamp"].str.endswith("Z").all() else "local time, no offset"
        lines.append(f"| {source} | {len(part):,} | {part['timestamp'].min()} | {part['timestamp'].max()} | {fmt} |")

    first, last = clean["timestamp"].min(), clean["timestamp"].max()
    lines += ["", "## Cleaning", "", "| Check | Result |", "|---|---:|",
              f"| Rows in | {log['rows_in']:,} |",
              f"| Timestamps converted from UTC to {TIMEZONE} | {log['utc_converted']:,} |",
              f"| Duplicates removed (same service and minute) | {log['duplicates_removed']:,} |",
              f"| Latency 0 ms set to missing | {log['zero_latency_set_missing']:,} |",
              f"| Rows out | {log['rows_out']:,} |",
              f"| Time range ({TIMEZONE}) | {first:%Y-%m-%d %H:%M} to {last:%H:%M} |",
              "", "## Missing values per column", "", "| Column | Missing |", "|---|---:|"]
    for col in ("p95_latency_ms", "error_rate_pct", "requests_per_min"):
        lines.append(f"| {col} | {int(clean[col].isna().sum())} |")

    lines += ["", "## Masked personal data", ""]
    if mask_counts is None:
        lines.append("Masking has not run yet (Task 4).")
    else:
        lines += ["| Item | Count |", "|---|---:|"]
        lines += [f"| {key} | {value} |" for key, value in mask_counts.items()]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
