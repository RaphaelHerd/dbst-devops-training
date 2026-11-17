"""Task 2 - Quality report and features (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 2)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import OUT_DIR, TIMEZONE


def add_features(clean: pd.DataFrame, changes: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Return a NEW table: the clean metrics plus hour, weekday, minutes_since_deployment, last_deployment_version
    and load_level.

    changes:  loaders.load_changes()        - deployments and config changes
    baseline: loaders.load_load_baseline()  - average requests per minute per service, weekday and hour (last week)
    """
    raise NotImplementedError("Task 2 - see .kiro/specs/opspilot-data/requirements.md, Requirement 2")


def write_quality_report(raw: pd.DataFrame, clean: pd.DataFrame, log: dict, mask_counts: dict | None = None,
                         path: Path = OUT_DIR / "data_quality.md") -> Path:
    """Write the data-quality report as Markdown to `path` and return the path.

    Content: exports (rows, first and last raw timestamp, time format), the cleaning log, missing values per
    metric column and the masking counts - or a note that masking has not run yet (mask_counts is None).
    """
    raise NotImplementedError("Task 2 - see .kiro/specs/opspilot-data/requirements.md, Requirement 2")
