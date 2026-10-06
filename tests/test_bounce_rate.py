"""
Tests for bounce rate calculation edge cases.
"""
from __future__ import annotations

import pytest

from app.services.aggregation_service import MailboxAggregate


def make_agg(sent: int, bounced: int) -> MailboxAggregate:
    agg = MailboxAggregate(
        email="test@example.com",
        normalized_email="test@example.com",
        smartlead_email_account_id=1,
        from_name=None,
        client_id=1,
        client_name="Client",
        sent=sent,
        bounced=bounced,
    )
    return agg


class TestBounceRateEdgeCases:

    def test_sent_500_bounced_10_rate_200(self):
        assert make_agg(500, 10).bounce_rate == 2.00

    def test_sent_500_bounced_8_rate_160(self):
        assert make_agg(500, 8).bounce_rate == 1.60

    def test_sent_700_bounced_14_rate_200(self):
        assert make_agg(700, 14).bounce_rate == 2.00

    def test_sent_350_bounced_4_rate_114(self):
        assert make_agg(350, 4).bounce_rate == 1.14

    def test_sent_0_bounced_0_rate_0(self):
        assert make_agg(0, 0).bounce_rate == 0.0

    def test_sent_0_bounced_positive_rate_0(self):
        """Even if bounced > 0 with sent=0, rate should be 0 (no division by zero)."""
        assert make_agg(0, 5).bounce_rate == 0.0

    def test_sent_1_bounced_1_rate_100(self):
        assert make_agg(1, 1).bounce_rate == 100.00

    def test_sent_1000_bounced_0_rate_0(self):
        assert make_agg(1000, 0).bounce_rate == 0.00

    def test_large_numbers(self):
        """Large numbers should not cause overflow or precision errors."""
        rate = make_agg(1_000_000, 12_345).bounce_rate
        expected = round((12_345 / 1_000_000) * 100, 2)
        assert rate == expected

    def test_result_is_float(self):
        assert isinstance(make_agg(100, 5).bounce_rate, float)

    def test_result_two_decimal_precision(self):
        """Result must have at most 2 decimal places."""
        rate = make_agg(333, 7).bounce_rate
        # 7/333*100 = 2.1021... → 2.1
        assert rate == round(rate, 2)
