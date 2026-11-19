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
    """Ask Claude on Amazon Bedrock for a one-sentence summary of the anomaly and the masked tickets."""
    if PERSONAL_COLUMNS & set(tickets.columns):
        raise ValueError("Unmasked tickets must not be sent to the LLM - run mask_tickets() first.")
    from anthropic import AnthropicBedrock                   # key: AWS_BEARER_TOKEN_BEDROCK from the environment

    client = AnthropicBedrock(aws_region=config.aws_region())
    response = client.messages.create(
        model=config.model_id(),                             # an inference profile ID, e.g. us.anthropic.claude-haiku-5-5
        max_tokens=1024,                                     # room for the model's thinking plus the short answer
        output_config={"effort": "low"},                     # short, simple task: low effort = fast and cheap
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(event, tickets)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined the request.")
    texts = [block.text for block in response.content if block.type == "text"]
    if not texts:
        raise RuntimeError(f"The answer contains no text (stop_reason: {response.stop_reason}).")
    return " ".join(text.strip() for text in texts)
