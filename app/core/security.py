"""
Security utilities.
Centralises all security-sensitive operations to make auditing easier.
"""
from __future__ import annotations

import re
from typing import Any


def mask_api_key(key: str) -> str:
    """
    Return a masked version of the API key suitable for logging.
    Shows first 4 and last 4 chars only.
    """
    if not key or len(key) < 10:
        return "****"
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def sanitize_url_for_logging(url: str) -> str:
    """
    Remove the api_key query parameter value from a URL before logging.
    Example:
        https://server.smartlead.ai/api/v1/campaigns?api_key=secret123
        → https://server.smartlead.ai/api/v1/campaigns?api_key=****
    """
    return re.sub(
        r"(api_key=)[^&\s]+",
        r"\1****",
        url,
        flags=re.IGNORECASE,
    )


def sanitize_log_message(message: str) -> str:
    """Remove any accidental API key or password from a log message."""
    # Remove api_key values
    message = re.sub(
        r"(api[_\-]?key[=:\s]+)[^\s&\"']+",
        r"\1****",
        message,
        flags=re.IGNORECASE,
    )
    # Remove bearer tokens
    message = re.sub(
        r"(bearer\s+)[^\s\"']+",
        r"\1****",
        message,
        flags=re.IGNORECASE,
    )
    return message


def validate_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def normalize_email(email: str) -> str:
    """
    Normalize an email address for deduplication.
    Lowercases the entire address.
    """
    return email.strip().lower()
