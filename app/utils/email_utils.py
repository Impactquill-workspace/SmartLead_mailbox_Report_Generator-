"""
Email address utilities.
Used for deduplication and normalization.
"""
from __future__ import annotations

import re


def normalize_email(email: str) -> str:
    """
    Normalize an email address for reliable deduplication.
    - Strip leading/trailing whitespace
    - Lowercase the entire address

    Note: We intentionally do NOT remove Gmail '+' aliases or dots,
    as this could incorrectly merge distinct sending addresses.
    """
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """Basic structural email validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def extract_domain(email: str) -> str:
    """Extract the domain part from an email address."""
    normalized = normalize_email(email)
    parts = normalized.split("@")
    if len(parts) == 2:
        return parts[1]
    return ""
