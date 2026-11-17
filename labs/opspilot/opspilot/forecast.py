"""Task 6 (stretch goal) - SLO forecast (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 6)."""
from __future__ import annotations

import pandas as pd


def forecast_error_budget(clean: pd.DataFrame, slo: pd.DataFrame, service: str = "payment-api",
                          window: str = "30min") -> dict:
    """Project when the error budget of a service runs out if the current burn rate continues.

    slo: loaders.load_slo(). Returns a dict with the keys service, budget_total_min, used_min, remaining_min,
    burn_rate, last_data and exhausted_at (a timestamp, or None if the budget is not burning).
    """
    raise NotImplementedError("Task 6 - see .kiro/specs/opspilot-data/requirements.md, Requirement 6")
