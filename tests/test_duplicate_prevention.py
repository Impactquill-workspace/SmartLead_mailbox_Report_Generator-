"""
Tests for duplicate prevention across all layers.
"""
from __future__ import annotations

import pytest

from app.services.aggregation_service import (
    MailboxAggregate,
    MailboxKey,
    aggregate_mailboxes,
)
from app.utils.email_utils import normalize_email


class TestEmailNormalization:

    def test_lowercase(self):
        assert normalize_email("TEST@EXAMPLE.COM") == "test@example.com"

    def test_strip_whitespace(self):
        assert normalize_email("  test@example.com  ") == "test@example.com"

    def test_already_lowercase(self):
        assert normalize_email("test@example.com") == "test@example.com"


class TestMailboxDeduplication:

    def test_same_smartlead_id_is_one_mailbox(self):
        """Two accounts with the same Smartlead ID should be treated as one mailbox."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 5,
                "email_accounts": [
                    {"id": 99, "from_email": "a@example.com"},
                ],
            },
            {
                "campaign_id": 2,
                "total_sent": 200,
                "total_bounced": 3,
                "email_accounts": [
                    {"id": 99, "from_email": "a@example.com"},
                ],
            },
        ]
        result = aggregate_mailboxes(1, "C", campaign_data)
        assert len(result) == 1
        assert result[0].sent == 300

    def test_different_smartlead_ids_different_mailboxes(self):
        """Two accounts with different Smartlead IDs are always different."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 5,
                "email_accounts": [
                    {"id": 1, "from_email": "same@example.com"},
                    {"id": 2, "from_email": "same@example.com"},
                ],
            },
        ]
        result = aggregate_mailboxes(1, "C", campaign_data)
        # With different IDs but same email, they are treated as different mailboxes
        # (ID takes precedence over email for deduplication)
        assert len(result) == 2

    def test_no_id_uses_email_for_dedup(self):
        """Without an ID, email is used for deduplication."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 5,
                "email_accounts": [{"id": None, "from_email": "test@example.com"}],
            },
            {
                "campaign_id": 2,
                "total_sent": 200,
                "total_bounced": 3,
                "email_accounts": [{"id": None, "from_email": "test@example.com"}],
            },
        ]
        result = aggregate_mailboxes(1, "C", campaign_data)
        assert len(result) == 1
        assert result[0].sent == 300

    def test_campaign_not_counted_twice_for_mailbox(self):
        """Adding the same campaign ID twice to a mailbox should only count once."""
        agg = MailboxAggregate(
            email="test@example.com",
            normalized_email="test@example.com",
            smartlead_email_account_id=1,
            from_name=None,
            client_id=1,
            client_name="C",
        )
        agg.add_campaign_stats(1, 100, 5, 1)
        agg.add_campaign_stats(1, 100, 5, 1)  # duplicate

        assert agg.sent == 100
        assert agg.bounced == 5
        assert len(agg.campaigns_contributed) == 1

    def test_empty_campaign_data(self):
        """Empty campaign mailbox data returns empty aggregates."""
        result = aggregate_mailboxes(1, "C", [])
        assert result == []

    def test_campaign_with_no_mailboxes(self):
        """Campaign with no email accounts contributes nothing."""
        campaign_data = [
            {
                "campaign_id": 1,
                "total_sent": 100,
                "total_bounced": 5,
                "email_accounts": [],
            }
        ]
        result = aggregate_mailboxes(1, "C", campaign_data)
        assert result == []
