"""Task 4 - Mask personal data (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 4)."""
from __future__ import annotations

import pandas as pd


def pseudonym(email: str) -> str:
    """A stable pseudonym such as CUST-3f9a1c: the same e-mail address always gives the same pseudonym."""
    raise NotImplementedError("Task 4 - see .kiro/specs/opspilot-data/requirements.md, Requirement 4")


def mask_tickets(tickets: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Minimise, pseudonymise and mask the tickets of loaders.load_tickets().

    Returns the masked tickets (ticket_id, created_at, service, customer, subject, description) and the counts of
    masked items with the keys email, ip, phone, name and customers_pseudonymised.
    """
    raise NotImplementedError("Task 4 - see .kiro/specs/opspilot-data/requirements.md, Requirement 4")
