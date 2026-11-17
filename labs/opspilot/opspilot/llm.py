"""Prompt building (ready) and Task 5 - Bedrock summary
(rules: .kiro/specs/opspilot-data/requirements.md, Requirement 5).
"""
from __future__ import annotations

import pandas as pd

from . import config
from .anomaly import AnomalyEvent

SYSTEM_PROMPT = ("You are an SRE assistant. Write exactly one sentence for the on-call channel. "
                 "State only facts from the data. Do not claim a root cause.")
PERSONAL_COLUMNS = {"customer_name", "customer_email"}


def select_recent_tickets(tickets: pd.DataFrame, since: pd.Timestamp, n: int = 3) -> pd.DataFrame:
    """The n most recent tickets created at or after `since`."""
    recent = tickets[tickets["created_at"] >= since].sort_values("created_at")
    return recent.tail(n)


def _fmt_ms(value: float) -> str:
    return f"{value / 1000:.1f} s" if value >= 1000 else f"{value:.0f} ms"


def build_prompt(event: AnomalyEvent, tickets: pd.DataFrame) -> str:
    """The user message for Claude: the anomaly event and the tickets, each inside clear delimiters."""
    lines = ["<anomaly>",
             f"service: {event.service}",
             f"metric: p95 latency",
             f"start: {event.start:%H:%M} ({event.start:%A, %d %B %Y})",
             f"baseline: {_fmt_ms(event.baseline_ms)}",
             f"peak: {_fmt_ms(event.peak_ms)}"]
    if event.deployment_version:
        lines.append(f"last deployment: {event.deployment_version}, "
                     f"{event.minutes_since_deployment:.0f} minutes before the start")
    lines += ["</anomaly>", "", "<tickets>"]
    for _, row in tickets.iterrows():
        lines.append("<ticket>")
        for col, value in row.items():
            if isinstance(value, pd.Timestamp):
                value = f"{value:%H:%M}"
            lines.append(f"{col}: {value}")
        lines.append("</ticket>")
    lines += ["</tickets>", "", "Summarise the situation for the on-call channel."]
    return "\n".join(lines)


def summarise_incident(event: AnomalyEvent, tickets: pd.DataFrame) -> str:
    """Ask Claude on Amazon Bedrock for a one-sentence summary of the anomaly and the MASKED tickets.

    Use an AnthropicBedrock client (anthropic[bedrock]) with the region from config.aws_region() and the model from
    config.model_id(). The SDK reads the API key from AWS_BEARER_TOKEN_BEDROCK.
    """
    raise NotImplementedError("Task 5 - see .kiro/specs/opspilot-data/requirements.md, Requirement 5")
