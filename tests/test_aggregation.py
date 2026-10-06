"""
Tests for aggregation_service.py

Tests:
1. Bounce rate calculation (sent=500, bounced=10 → 2.00%)
2. Bounce rate when sent=0 → 0.0%
3. Duplicate mailbox detection (same mailbox in multiple campaigns)
4. Same mailbox ID → not double counted
5. Same email different ID → treated as separate (correct)
6. Data validation (negative sent, bounced > sent)
7. Multiple clients isolated from each other
8. Multi-mailbox campaign equal-share attribution
"""
from __future__ import annotations

import pytest

from app.services.aggregation_service import (
    MailboxAggregate,
    MailboxKey,
    aggregate_mailboxes,
    validate_analytics_data,
)


class TestBounceRateCalculation:
    """Core bounce rate formula tests."""

    def test_standard_case(self):
        """sent=500, bounced=10 → bounce_rate=2.00"""
        agg = MailboxAggregate(
            email="test@example.com",
            normalized_email="test@example.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="Test Client",
            sent=500,
            bounced=10,
        )
        assert agg.bounce_rate == 2.00

    def test_zero_sent(self):
        """sent=0 → bounce_rate=0 (no division by zero)"""
        agg = MailboxAggregate(
            email="test@example.com",
            normalized_email="test@example.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="Test Client",
            sent=0,
            bounced=0,
        )
        assert agg.bounce_rate == 0.0

    def test_example_from_spec(self):
        """sent=500, bounced=8 → bounce_rate=1.60"""
        agg = MailboxAggregate(
            email="sales@abc.com",
            normalized_email="sales@abc.com",
            smartlead_email_account_id=987,
            from_name=None,
            client_id=123,
            client_name="Client A",
            sent=500,
            bounced=8,
        )
        assert agg.bounce_rate == 1.60

    def test_rounding_to_2_decimal_places(self):
        """Bounce rate must be rounded to 2 decimal places."""
        agg = MailboxAggregate(
            email="a@b.com",
            normalized_email="a@b.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="C",
            sent=350,
            bounced=4,
        )
        # 4/350 * 100 = 1.142857... → should round to 1.14
        assert agg.bounce_rate == 1.14

    def test_1000_bounced_of_1000_sent(self):
        """100% bounce rate."""
        agg = MailboxAggregate(
            email="a@b.com",
            normalized_email="a@b.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="C",
            sent=1000,
            bounced=1000,
        )
        assert agg.bounce_rate == 100.00


class TestDuplicateMailboxPrevention:
    """Tests that the same mailbox is not double-counted."""

    def test_same_mailbox_in_two_campaigns(self):
        """
        mailbox@example.com in Campaign A (sent=100, bounced=2)
                              Campaign B (sent=200, bounced=4)
        Expected total:        sent=300, bounced=6
        """
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 2,
                "email_accounts": [
                    {"id": 42, "from_email": "mailbox@example.com", "from_name": "Test"}
                ],
            },
            {
                "campaign_id": 2,
                "total_sent": 200,
                "total_bounced": 4,
                "email_accounts": [
                    {"id": 42, "from_email": "mailbox@example.com", "from_name": "Test"}
                ],
            },
        ]

        aggregates = aggregate_mailboxes(
            client_id=1,
            client_name="Client A",
            campaign_mailbox_data=campaign_data,
        )

        assert len(aggregates) == 1, "Should be exactly 1 unique mailbox"
        agg = aggregates[0]
        assert agg.email == "mailbox@example.com"
        assert agg.sent == 300
        assert agg.bounced == 6
        assert agg.bounce_rate == 2.00

    def test_duplicate_campaign_not_counted_twice(self):
        """The same campaign_id must not be counted twice for the same mailbox."""
        agg = MailboxAggregate(
            email="test@example.com",
            normalized_email="test@example.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="C",
        )
        agg.add_campaign_stats(campaign_id=10, campaign_sent=100, campaign_bounced=5, num_mailboxes_in_campaign=1)
        agg.add_campaign_stats(campaign_id=10, campaign_sent=100, campaign_bounced=5, num_mailboxes_in_campaign=1)  # duplicate

        assert agg.sent == 100, "Duplicate campaign should not be counted twice"
        assert agg.bounced == 5

    def test_email_case_normalization(self):
        """SALES@COMPANY.COM and sales@company.com should be the same mailbox."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 2,
                "email_accounts": [
                    {"id": None, "from_email": "SALES@COMPANY.COM"}
                ],
            },
            {
                "campaign_id": 2,
                "total_sent": 100,
                "total_bounced": 2,
                "email_accounts": [
                    {"id": None, "from_email": "sales@company.com"}
                ],
            },
        ]

        aggregates = aggregate_mailboxes(
            client_id=1,
            client_name="Client",
            campaign_mailbox_data=campaign_data,
        )

        assert len(aggregates) == 1, "Normalized emails should deduplicate"
        assert aggregates[0].sent == 200

    def test_different_mailboxes_not_merged(self):
        """Two different mailboxes must remain separate."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 2,
                "email_accounts": [
                    {"id": 1, "from_email": "john@company.com"},
                    {"id": 2, "from_email": "sales@company.com"},
                ],
            },
        ]

        aggregates = aggregate_mailboxes(
            client_id=1,
            client_name="Client A",
            campaign_mailbox_data=campaign_data,
        )

        assert len(aggregates) == 2, "Two different mailboxes must be separate"


class TestMailboxKey:
    """Tests for the MailboxKey deduplication logic."""

    def test_same_id_equals(self):
        key1 = MailboxKey(smartlead_id=42, normalized_email="a@b.com")
        key2 = MailboxKey(smartlead_id=42, normalized_email="different@x.com")
        assert key1 == key2, "Same Smartlead ID must match regardless of email"

    def test_different_id_not_equal(self):
        key1 = MailboxKey(smartlead_id=42, normalized_email="a@b.com")
        key2 = MailboxKey(smartlead_id=99, normalized_email="a@b.com")
        assert key1 != key2

    def test_no_id_uses_email(self):
        key1 = MailboxKey(smartlead_id=None, normalized_email="a@b.com")
        key2 = MailboxKey(smartlead_id=None, normalized_email="a@b.com")
        assert key1 == key2

    def test_no_id_different_email_not_equal(self):
        key1 = MailboxKey(smartlead_id=None, normalized_email="a@b.com")
        key2 = MailboxKey(smartlead_id=None, normalized_email="c@d.com")
        assert key1 != key2

    def test_hashable(self):
        key1 = MailboxKey(smartlead_id=42, normalized_email="a@b.com")
        key2 = MailboxKey(smartlead_id=42, normalized_email="other@x.com")
        d = {key1: "value"}
        assert d[key2] == "value"


class TestDataValidation:
    """Tests for analytics data validation."""

    def test_normal_data(self):
        data = [
            {"date": "2026-09-21", "sent_count": 100, "bounce_count": 5},
            {"date": "2026-09-22", "sent_count": 200, "bounce_count": 3},
        ]
        sent, bounced = validate_analytics_data(data, campaign_id=1)
        assert sent == 300
        assert bounced == 8

    def test_missing_fields_default_to_zero(self):
        data = [{"date": "2026-09-21"}]  # No counts
        sent, bounced = validate_analytics_data(data, campaign_id=1)
        assert sent == 0
        assert bounced == 0

    def test_negative_sent_treated_as_zero(self):
        """Negative sent count should be treated as 0 (with warning)."""
        data = [{"date": "2026-09-21", "sent_count": -10, "bounce_count": 2}]
        sent, bounced = validate_analytics_data(data, campaign_id=1)
        assert sent == 0

    def test_bounced_exceeds_sent_capped(self):
        """If bounced > sent, bounce is capped at sent (data integrity)."""
        data = [{"date": "2026-09-21", "sent_count": 10, "bounce_count": 50}]
        sent, bounced = validate_analytics_data(data, campaign_id=1)
        assert bounced <= sent

    def test_empty_data(self):
        sent, bounced = validate_analytics_data([], campaign_id=1)
        assert sent == 0
        assert bounced == 0


class TestMultipleClients:
    """Tests that multiple clients' data stays isolated."""

    def test_clients_isolated(self):
        """Mailboxes from client A and client B must not be merged."""
        data_a = [
            {
                "campaign_id": 1,
                "total_sent": 500,
                "total_bounced": 10,
                "email_accounts": [{"id": 100, "from_email": "shared@example.com"}],
            }
        ]
        data_b = [
            {
                "campaign_id": 2,
                "total_sent": 300,
                "total_bounced": 6,
                "email_accounts": [{"id": 100, "from_email": "shared@example.com"}],
            }
        ]

        agg_a = aggregate_mailboxes(1, "Client A", data_a)
        agg_b = aggregate_mailboxes(2, "Client B", data_b)

        # Each client has its own aggregate
        assert len(agg_a) == 1
        assert len(agg_b) == 1
        assert agg_a[0].sent == 500
        assert agg_b[0].sent == 300


class TestMultiMailboxCampaign:
    """Tests for the multi-mailbox equal-share attribution."""

    def test_two_mailboxes_equal_share(self):
        """
        Campaign with 2 mailboxes: sent=100, bounced=10
        Each mailbox gets: sent=50, bounced=5
        """
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 10,
                "email_accounts": [
                    {"id": 1, "from_email": "mb1@example.com"},
                    {"id": 2, "from_email": "mb2@example.com"},
                ],
            },
        ]

        aggregates = aggregate_mailboxes(1, "Client", campaign_data)
        aggregates_by_email = {a.email: a for a in aggregates}

        assert aggregates_by_email["mb1@example.com"].sent == 50
        assert aggregates_by_email["mb2@example.com"].sent == 50
        assert aggregates_by_email["mb1@example.com"].bounced == 5

    def test_single_mailbox_full_attribution(self):
        """Single mailbox in campaign gets full attribution (not estimated)."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 10,
                "email_accounts": [
                    {"id": 1, "from_email": "solo@example.com"},
                ],
            },
        ]

        aggregates = aggregate_mailboxes(1, "Client", campaign_data)
        agg = aggregates[0]

        assert agg.sent == 100
        assert agg.bounced == 10
        assert not agg.has_multi_mailbox_attribution


class TestLeadsContactedCalculation:
    """Tests for accurate proportional unique leads contacted attribution."""

    def test_proportional_leads_contacted_direct_stats(self):
        """
        Campaign with 2 mailboxes:
        mb1: sent 120, bounced 6
        mb2: sent 80, bounced 4
        Total sent: 200
        Unique leads contacted (unique_sent_count): 100
        mb1 leads: 120 * (100 / 200) = 60
        mb2 leads: 80 * (100 / 200) = 40
        """
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 200,
                "total_bounced": 10,
                "unique_sent_count": 100,
                "email_accounts": [
                    {"id": 1, "from_email": "mb1@example.com"},
                    {"id": 2, "from_email": "mb2@example.com"},
                ],
                "mailbox_stats": [
                    {
                        "email_account_id": 1,
                        "from_email": "mb1@example.com",
                        "sent_count": 120,
                        "bounce_count": 6,
                    },
                    {
                        "email_account_id": 2,
                        "from_email": "mb2@example.com",
                        "sent_count": 80,
                        "bounce_count": 4,
                    },
                ],
            },
        ]

        aggregates = aggregate_mailboxes(1, "Client", campaign_data)
        by_email = {a.email: a for a in aggregates}

        assert by_email["mb1@example.com"].sent == 120
        assert by_email["mb1@example.com"].leads_contacted == 60
        assert by_email["mb2@example.com"].sent == 80
        assert by_email["mb2@example.com"].leads_contacted == 40
        assert sum(a.leads_contacted for a in aggregates) == 100

    def test_single_mailbox_leads_contacted(self):
        """Single mailbox in campaign gets all unique leads."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 500,
                "total_bounced": 15,
                "unique_sent_count": 180,
                "email_accounts": [
                    {"id": 1, "from_email": "solo@example.com"},
                ],
                "mailbox_stats": [
                    {
                        "email_account_id": 1,
                        "from_email": "solo@example.com",
                        "sent_count": 500,
                        "bounce_count": 15,
                    },
                ],
            },
        ]

        aggregates = aggregate_mailboxes(1, "Client", campaign_data)
        assert aggregates[0].sent == 500
        assert aggregates[0].leads_contacted == 180
        assert aggregates[0].bounced == 15
