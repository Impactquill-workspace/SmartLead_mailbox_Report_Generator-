"""
Custom exception hierarchy for Smartlead API errors.
Separates recoverable from non-recoverable failures.
"""
from __future__ import annotations


class SmartleadError(Exception):
    """Base class for all Smartlead-related errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SmartleadAuthError(SmartleadError):
    """
    Authentication failure (401 / 403).
    Non-recoverable — do NOT retry; fix the API key.
    """


class SmartleadNotFoundError(SmartleadError):
    """Resource not found (404)."""


class SmartleadRateLimitError(SmartleadError):
    """
    Rate limit exceeded (429).
    Recoverable — retry after backing off.
    """

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after  # seconds to wait, if provided by Retry-After header


class SmartleadServerError(SmartleadError):
    """
    Server-side error (5xx).
    Recoverable — retry with exponential backoff.
    """


class SmartleadValidationError(SmartleadError):
    """
    Unexpected / missing fields in API response.
    Logged as a warning — report produced with available data.
    """


class SmartleadNetworkError(SmartleadError):
    """
    Network-level failure (timeout, connection refused, etc.).
    Recoverable — retry with exponential backoff.
    """
