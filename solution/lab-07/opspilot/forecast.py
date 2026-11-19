"""Task 6 (stretch goal) - SLO forecast (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 6)."""
from __future__ import annotations

import pandas as pd


def forecast_error_budget(clean: pd.DataFrame, slo: pd.DataFrame, service: str = "payment-api",
                          window: str = "30min") -> dict:
    """Project when the error budget of a service runs out if the current burn rate continues."""
    target = slo.set_index("service").loc[service]
    budget_total = (1 - target["target_pct"] / 100) * target["window_days"] * 24 * 60
    latency = clean[clean["service"] == service].set_index("timestamp")["p95_latency_ms"].dropna()
    bad = latency > target["slo_p95_ms"]

    bad_today = int(bad.sum())
    used = int(target["bad_minutes_before_today"]) + bad_today
    remaining = max(budget_total - used, 0.0)
    last = latency.index.max()
    burn_rate = float(bad[bad.index > last - pd.Timedelta(window)].mean())      # bad minutes per minute

    exhausted_at = None
    if remaining == 0:
        exhausted_at = last
    elif burn_rate > 0:
        exhausted_at = last + pd.Timedelta(minutes=remaining / burn_rate)
    return {"service": service, "budget_total_min": round(budget_total), "used_min": used,
            "remaining_min": round(remaining), "burn_rate": round(burn_rate, 2), "last_data": last,
            "exhausted_at": exhausted_at}
