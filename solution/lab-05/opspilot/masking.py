"""Task 4 - Mask personal data (rules: .kiro/specs/opspilot-data/requirements.md, Requirement 4)."""
from __future__ import annotations

import hashlib
import os
import re

import pandas as pd

KEEP = ["ticket_id", "created_at", "service", "subject", "description"]     # data minimisation
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE = re.compile(r"(?:\+\d{2,3}|\b0\d)[\d /-]{6,}\d")


def pseudonym(email: str) -> str:
    """A stable pseudonym such as CUST-3f9a1c: the same e-mail address always gives the same pseudonym."""
    salt = os.environ.get("OPSPILOT_PSEUDONYM_SALT", "opspilot-workshop")
    digest = hashlib.sha256((salt + email.strip().lower()).encode("utf-8")).hexdigest()
    return f"CUST-{digest[:6]}"


def mask_text(text: str, customer_name: str, customer: str, counts: dict) -> str:
    """Mask e-mail addresses, IP addresses, phone numbers and the customer's own name in one text."""
    text, n = EMAIL.subn("<EMAIL>", text)
    counts["email"] += n
    text, n = IPV4.subn("<IP>", text)
    counts["ip"] += n
    text, n = PHONE.subn("<PHONE>", text)
    counts["phone"] += n
    if customer_name:
        text, n = re.subn(re.escape(customer_name), customer, text, flags=re.IGNORECASE)
        counts["name"] += n
    return text


def mask_tickets(tickets: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Minimise, pseudonymise and mask the tickets.

    Returns the masked tickets (ticket_id, created_at, service, customer, subject, description) and the counts of
    masked items.
    """
    counts = {"email": 0, "ip": 0, "phone": 0, "name": 0}
    customers = tickets["customer_email"].fillna("").map(pseudonym)
    masked = tickets[KEEP].copy()
    masked.insert(3, "customer", customers)
    for col in ("subject", "description"):
        masked[col] = [mask_text(str(text), str(name), customer, counts)
                       for text, name, customer in zip(tickets[col].fillna(""), tickets["customer_name"].fillna(""),
                                                       customers)]
    counts["customers_pseudonymised"] = int(customers.nunique())
    return masked, counts
