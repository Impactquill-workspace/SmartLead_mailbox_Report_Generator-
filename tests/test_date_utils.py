"""
Tests for date_utils.py

Tests:
1. Previous week calculation — correct Monday
2. Monday–Sunday date range
3. Current week calculation
4. parse_date
5. validate_date_range
6. split_into_30_day_chunks
7. Edge: report on a Monday
8. Edge: report on a Sunday
"""
from __future__ import annotations

from datetime import date

import pytest

from app.utils.date_utils import (
    DateRange,
    get_current_calendar_week,
    get_previous_calendar_week,
    parse_date,
    split_into_30_day_chunks,
    validate_date_range,
)


class TestGetPreviousCalendarWeek:
    """Previous calendar week calculation tests."""

    def test_from_wednesday(self):
        """Wednesday Sep 30 2026 → previous week: Sep 21–27 2026"""
        ref = date(2026, 9, 30)  # Wednesday
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 9, 21), "Start must be Monday"
        assert result.end == date(2026, 9, 27), "End must be Sunday"

    def test_from_monday(self):
        """Monday Sep 28 2026 → previous week: Sep 21–27 2026"""
        ref = date(2026, 9, 28)  # Monday
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 9, 21)
        assert result.end == date(2026, 9, 27)

    def test_from_sunday(self):
        """Sunday Sep 27 2026 → previous week: Sep 14–20 2026"""
        ref = date(2026, 9, 27)  # Sunday
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 9, 14)
        assert result.end == date(2026, 9, 20)

    def test_from_friday(self):
        """Friday Oct 2 2026 → previous week: Sep 21–27 2026"""
        ref = date(2026, 10, 2)
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 9, 21)
        assert result.end == date(2026, 9, 27)

    def test_start_is_monday(self):
        """Start day must always be a Monday (weekday == 0)."""
        for day_offset in range(7):
            ref = date(2026, 9, 28) + __import__("datetime").timedelta(days=day_offset)
            result = get_previous_calendar_week(ref)
            assert result.start.weekday() == 0, (
                f"Start must be Monday for ref={ref}, got {result.start.strftime('%A')}"
            )

    def test_end_is_sunday(self):
        """End day must always be a Sunday (weekday == 6)."""
        for day_offset in range(7):
            ref = date(2026, 9, 28) + __import__("datetime").timedelta(days=day_offset)
            result = get_previous_calendar_week(ref)
            assert result.end.weekday() == 6, (
                f"End must be Sunday for ref={ref}"
            )

    def test_exactly_7_days(self):
        """Period must be exactly 7 days."""
        from datetime import timedelta
        ref = date(2026, 9, 30)
        result = get_previous_calendar_week(ref)
        delta = result.end - result.start
        assert delta.days == 6  # inclusive: Mon→Sun = 6 days gap

    def test_not_rolling_7_days(self):
        """Must be calendar week, NOT rolling 7×24 hours."""
        ref_wed = date(2026, 9, 30)  # Wednesday
        result = get_previous_calendar_week(ref_wed)
        # Rolling 7 days from Wednesday would give: Wed 23 Sep → Tue 29 Sep
        # But calendar week gives: Mon 21 Sep → Sun 27 Sep
        assert result.start == date(2026, 9, 21), "Must use calendar week, not rolling window"
        assert result.end == date(2026, 9, 27)

    def test_cross_month_boundary(self):
        """Works correctly when previous week crosses month boundary."""
        ref = date(2026, 10, 5)  # Monday
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 9, 28)
        assert result.end == date(2026, 10, 4)

    def test_cross_year_boundary(self):
        """Works correctly when previous week crosses year boundary."""
        ref = date(2027, 1, 4)  # Monday
        result = get_previous_calendar_week(ref)
        assert result.start == date(2026, 12, 28)
        assert result.end == date(2027, 1, 3)


class TestGetCurrentCalendarWeek:
    def test_from_wednesday(self):
        ref = date(2026, 9, 30)
        result = get_current_calendar_week(ref)
        assert result.start == date(2026, 9, 28)
        assert result.end == date(2026, 10, 4)


class TestParseDate:
    def test_valid_date(self):
        assert parse_date("2026-09-21") == date(2026, 9, 21)

    def test_with_whitespace(self):
        assert parse_date("  2026-09-21  ") == date(2026, 9, 21)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date("21-09-2026")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            parse_date("2026-13-01")


class TestValidateDateRange:
    def test_valid_range(self):
        validate_date_range(date(2026, 9, 21), date(2026, 9, 27))  # Should not raise

    def test_same_day(self):
        validate_date_range(date(2026, 9, 21), date(2026, 9, 21))  # Should not raise

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError, match="must be before or equal to"):
            validate_date_range(date(2026, 9, 27), date(2026, 9, 21))

    def test_too_long_range_raises(self):
        with pytest.raises(ValueError, match="exceeds 365 days"):
            validate_date_range(date(2025, 1, 1), date(2026, 12, 31))


class TestSplitInto30DayChunks:
    def test_7_day_range_single_chunk(self):
        chunks = split_into_30_day_chunks(date(2026, 9, 21), date(2026, 9, 27))
        assert len(chunks) == 1
        assert chunks[0].start == date(2026, 9, 21)
        assert chunks[0].end == date(2026, 9, 27)

    def test_30_day_range_single_chunk(self):
        chunks = split_into_30_day_chunks(date(2026, 9, 1), date(2026, 9, 30))
        assert len(chunks) == 1

    def test_31_day_range_two_chunks(self):
        chunks = split_into_30_day_chunks(date(2026, 9, 1), date(2026, 10, 1))
        assert len(chunks) == 2
        assert chunks[0].end == date(2026, 9, 30)
        assert chunks[1].start == date(2026, 10, 1)
        assert chunks[1].end == date(2026, 10, 1)

    def test_chunks_are_contiguous(self):
        """No gaps between chunks."""
        from datetime import timedelta
        chunks = split_into_30_day_chunks(date(2026, 1, 1), date(2026, 12, 31))
        for i in range(len(chunks) - 1):
            assert chunks[i + 1].start == chunks[i].end + timedelta(days=1)

    def test_chunks_cover_full_range(self):
        start = date(2026, 1, 1)
        end = date(2026, 12, 31)
        chunks = split_into_30_day_chunks(start, end)
        assert chunks[0].start == start
        assert chunks[-1].end == end
