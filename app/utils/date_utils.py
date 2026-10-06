"""
Date calculation utilities.

Primary requirement: previous calendar week (Monday–Sunday).
All date arithmetic uses calendar-week logic, NOT rolling 7-day windows.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple


class DateRange(NamedTuple):
    """An inclusive date range."""
    start: date
    end: date

    def __str__(self) -> str:
        return f"{self.start.isoformat()} to {self.end.isoformat()}"


def get_previous_calendar_week(reference_date: date | None = None) -> DateRange:
    """
    Return the previous calendar week as Monday 00:00 → Sunday 23:59.

    Calendar week definition: ISO week — Monday is day 1, Sunday is day 7.

    Example:
        If today is Wednesday 2026-09-30,
        the previous week is Monday 2026-09-21 → Sunday 2026-09-27.

    Args:
        reference_date: The date to calculate 'previous week' from.
                        Defaults to today (UTC).

    Returns:
        DateRange(start=Monday, end=Sunday) of the previous calendar week.
    """
    if reference_date is None:
        reference_date = date.today()

    # Find the Monday of the CURRENT week
    # weekday() returns 0=Monday … 6=Sunday
    days_since_monday = reference_date.weekday()  # 0 for Mon, 6 for Sun
    current_monday = reference_date - timedelta(days=days_since_monday)

    # Previous week: one week before current Monday
    prev_monday = current_monday - timedelta(weeks=1)
    prev_sunday = prev_monday + timedelta(days=6)

    return DateRange(start=prev_monday, end=prev_sunday)


def get_current_calendar_week(reference_date: date | None = None) -> DateRange:
    """Return the current calendar week (Monday → Sunday)."""
    if reference_date is None:
        reference_date = date.today()

    days_since_monday = reference_date.weekday()
    current_monday = reference_date - timedelta(days=days_since_monday)
    current_sunday = current_monday + timedelta(days=6)

    return DateRange(start=current_monday, end=current_sunday)


def parse_date(date_str: str) -> date:
    """
    Parse a YYYY-MM-DD string into a date object.

    Raises:
        ValueError: If the format is not YYYY-MM-DD.
    """
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Invalid date format: {date_str!r}. Expected YYYY-MM-DD."
        ) from exc


def validate_date_range(start: date, end: date) -> None:
    """
    Validate that start <= end and the range is not more than 365 days.

    Raises:
        ValueError: If the range is invalid.
    """
    if start > end:
        raise ValueError(
            f"start_date ({start}) must be before or equal to end_date ({end})"
        )
    if (end - start).days > 365:
        raise ValueError(
            f"Date range ({start} → {end}) exceeds 365 days. "
            "Split into smaller ranges for reliable API results."
        )


def split_into_30_day_chunks(start: date, end: date) -> list[DateRange]:
    """
    Split a date range into chunks of at most 30 days.

    Smartlead's analytics-by-date endpoint has a 30-day maximum span.
    This function splits longer ranges into compliant chunks.

    Args:
        start: Start of the full date range.
        end: End of the full date range.

    Returns:
        List of DateRange objects, each spanning at most 30 days.
    """
    validate_date_range(start, end)
    chunks: list[DateRange] = []
    chunk_start = start

    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=29), end)
        chunks.append(DateRange(start=chunk_start, end=chunk_end))
        chunk_start = chunk_end + timedelta(days=1)

    return chunks


def format_date(d: date) -> str:
    """Format a date as YYYY-MM-DD string."""
    return d.isoformat()
