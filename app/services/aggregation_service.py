"""
Aggregation service.

Core business logic: aggregate campaign-level analytics to mailbox level.

IMPORTANT DESIGN DECISION (documented here and in README):
=============================================================
Smartlead's GET /campaigns/{id}/analytics-by-date endpoint returns
CAMPAIGN-LEVEL daily statistics, NOT mailbox-level statistics.

There is NO official Smartlead API endpoint that provides historical
sent/bounced counts attributed to an individual mailbox for a custom
date range.

Our approach:
1. For each campaign, fetch daily analytics over the period.
2. Sum: total_sent + total_bounced for the campaign.
3. Fetch which mailboxes (email accounts) are attached to that campaign.
4. If a campaign has exactly 1 mailbox → attribute all stats to that mailbox.
5. If a campaign has N mailboxes (N > 1):
   - We CANNOT split stats fairly between mailboxes without real send logs.
   - We record the campaign stats against ALL mailboxes proportionally
     BUT clearly flag this in the data with `attribution_method`.
   - The bounce_rate calculation is still valid (it's a ratio).
   - The `sent` / `bounced` absolute counts ARE an estimate in this case.
6. Deduplicate mailboxes by smartlead_email_account_id (preferred) or
   normalized email (fallback). Aggregate across campaigns.

This is the most accurate approach available with the current Smartlead API.
The README and the API response include a clear disclosure of this limitation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from app.core.security import normalize_email
from app.schemas.analytics import DailyAnalytics

logger = logging.getLogger(__name__)


class MailboxKey(NamedTuple):
    """Unique identifier for a mailbox — prefers Smartlead ID over email."""
    smartlead_id: int | None
    normalized_email: str

    @classmethod
    def from_account(cls, account: dict[str, Any]) -> "MailboxKey":
        smartlead_id = account.get("id")
        email = account.get("from_email", "") or account.get("email", "")
        return cls(
            smartlead_id=int(smartlead_id) if smartlead_id else None,
            normalized_email=normalize_email(email),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MailboxKey):
            return NotImplemented
        # If both have a Smartlead ID, use it as the sole key
        if self.smartlead_id is not None and other.smartlead_id is not None:
            return self.smartlead_id == other.smartlead_id
        # Fall back to email comparison
        return self.normalized_email == other.normalized_email

    def __hash__(self) -> int:
        if self.smartlead_id is not None:
            return hash(("id", self.smartlead_id))
        return hash(("email", self.normalized_email))


@dataclass
class MailboxAggregate:
    """Running aggregate for a single mailbox across all campaigns."""
    email: str
    normalized_email: str
    smartlead_email_account_id: int | None
    from_name: str | None
    client_id: int | None
    client_name: str | None

    # Running totals (deduplicated across campaigns)
    sent: int = 0
    bounced: int = 0

    # Attribution tracking
    campaigns_contributed: list[int] = field(default_factory=list)
    multi_mailbox_campaigns: list[int] = field(default_factory=list)

    def add_campaign_stats(
        self,
        campaign_id: int,
        campaign_sent: int,
        campaign_bounced: int,
        num_mailboxes_in_campaign: int,
    ) -> None:
        """
        Add one campaign's contribution to this mailbox.

        If this is the only mailbox in the campaign: full attribution.
        If multiple mailboxes: equal-share attribution (documented limitation).
        """
        if campaign_id in self.campaigns_contributed:
            logger.debug(
                "Skipping duplicate campaign %d for mailbox %s",
                campaign_id,
                self.normalized_email,
            )
            return

        if num_mailboxes_in_campaign <= 0:
            return

        if num_mailboxes_in_campaign == 1:
            # Full attribution — accurate
            attributed_sent = campaign_sent
            attributed_bounced = campaign_bounced
        else:
            # Equal-share attribution — documented estimate
            attributed_sent = campaign_sent // num_mailboxes_in_campaign
            attributed_bounced = campaign_bounced // num_mailboxes_in_campaign
            self.multi_mailbox_campaigns.append(campaign_id)
            logger.debug(
                "Multi-mailbox campaign %d: %d mailboxes, attributing %d/%d "
                "sent/bounced to %s (equal-share estimate)",
                campaign_id,
                num_mailboxes_in_campaign,
                attributed_sent,
                attributed_bounced,
                self.normalized_email,
            )

        self.sent += attributed_sent
        self.bounced += attributed_bounced
        self.campaigns_contributed.append(campaign_id)

    def add_direct_stats(
        self,
        campaign_id: int,
        sent: int,
        bounced: int,
    ) -> None:
        """
        Add exact mailbox sent and bounce counts from /campaigns/{id}/mailbox-statistics.
        Prevents double-counting if the campaign was already contributed.
        """
        if campaign_id in self.campaigns_contributed:
            logger.debug(
                "Skipping duplicate direct campaign %d for mailbox %s",
                campaign_id,
                self.normalized_email,
            )
            return

        self.sent += max(0, sent)
        self.bounced += max(0, bounced)
        self.campaigns_contributed.append(campaign_id)

    @property
    def bounce_rate(self) -> float:
        """
        Bounce rate as a percentage.
        bounce_rate = (bounced / sent) * 100
        Returns 0 if sent == 0 (no division by zero).
        """
        if self.sent == 0:
            return 0.0
        return round((self.bounced / self.sent) * 100, 2)

    @property
    def has_multi_mailbox_attribution(self) -> bool:
        """True if any stats were estimated via equal-share attribution."""
        return len(self.multi_mailbox_campaigns) > 0


def validate_analytics_data(
    daily_data: list[dict[str, Any]],
    campaign_id: int,
) -> tuple[int, int]:
    """
    Parse and validate analytics data from Smartlead.

    Validates:
    - sent >= 0
    - bounced >= 0
    - bounced <= sent (warns but doesn't raise)

    Returns:
        (total_sent, total_bounced) for the period.
    """
    total_sent = 0
    total_bounced = 0

    for day_data in daily_data:
        analytics = DailyAnalytics.from_api_response(day_data)

        if analytics.sent_count < 0:
            logger.warning(
                "Campaign %d: negative sent_count (%d) on %s — treating as 0",
                campaign_id,
                analytics.sent_count,
                analytics.date,
            )
            analytics = analytics.model_copy(update={"sent_count": 0})

        if analytics.bounce_count < 0:
            logger.warning(
                "Campaign %d: negative bounce_count (%d) on %s — treating as 0",
                campaign_id,
                analytics.bounce_count,
                analytics.date,
            )
            analytics = analytics.model_copy(update={"bounce_count": 0})

        if analytics.bounce_count > analytics.sent_count and analytics.sent_count > 0:
            logger.warning(
                "Campaign %d: bounce_count (%d) > sent_count (%d) on %s — "
                "data integrity issue from Smartlead. Capping bounced at sent.",
                campaign_id,
                analytics.bounce_count,
                analytics.sent_count,
                analytics.date,
            )
            analytics = analytics.model_copy(
                update={"bounce_count": analytics.sent_count}
            )

        total_sent += analytics.sent_count
        total_bounced += analytics.bounce_count

    return total_sent, total_bounced


def aggregate_mailboxes(
    client_id: int,
    client_name: str,
    campaign_mailbox_data: list[dict[str, Any]],
) -> list[MailboxAggregate]:
    """
    Aggregate analytics across all campaigns for a client into per-mailbox totals.

    Args:
        client_id: Smartlead client ID.
        client_name: Human-readable client name.
        campaign_mailbox_data: List of dicts with shape:
            {
                "campaign_id": int,
                "total_sent": int,
                "total_bounced": int,
                "email_accounts": [
                    {"id": int, "from_email": str, "from_name": str, ...}
                ]
            }

    Returns:
        List of MailboxAggregate objects, one per unique mailbox.
    """
    mailbox_map: dict[MailboxKey, MailboxAggregate] = {}

    for campaign_data in campaign_mailbox_data:
        campaign_id = campaign_data["campaign_id"]
        campaign_sent = campaign_data.get("total_sent", 0)
        campaign_bounced = campaign_data.get("total_bounced", 0)
        email_accounts = campaign_data.get("email_accounts", [])

        if not email_accounts:
            logger.debug(
                "Campaign %d has no email accounts — skipping analytics",
                campaign_id,
            )
            continue

        mailbox_stats = campaign_data.get("mailbox_stats")

        if mailbox_stats is not None:
            # DIRECT OFFICIAL ATTRIBUTION via /campaigns/{id}/mailbox-statistics
            stats_by_acc_id: dict[int, dict[str, Any]] = {}
            stats_by_email: dict[str, dict[str, Any]] = {}
            for stat in mailbox_stats:
                acc_id = stat.get("email_account_id")
                if acc_id:
                    stats_by_acc_id[int(acc_id)] = stat
                from_em = normalize_email(stat.get("from_email", ""))
                if from_em:
                    stats_by_email[from_em] = stat

            # Register all attached email accounts
            for account in email_accounts:
                key = MailboxKey.from_account(account)
                email = account.get("from_email", "") or account.get("email", "")

                if key not in mailbox_map:
                    mailbox_map[key] = MailboxAggregate(
                        email=email,
                        normalized_email=key.normalized_email,
                        smartlead_email_account_id=key.smartlead_id,
                        from_name=account.get("from_name"),
                        client_id=client_id,
                        client_name=client_name,
                    )

                stat_match = None
                if key.smartlead_id and key.smartlead_id in stats_by_acc_id:
                    stat_match = stats_by_acc_id[key.smartlead_id]
                elif key.normalized_email in stats_by_email:
                    stat_match = stats_by_email[key.normalized_email]

                if stat_match:
                    s_count = int(stat_match.get("sent_count", 0) or 0)
                    b_count = int(stat_match.get("bounce_count", 0) or 0)
                    mailbox_map[key].add_direct_stats(campaign_id, s_count, b_count)

            # Also register any mailbox that sent emails but wasn't in attached email_accounts
            for stat in mailbox_stats:
                acc_id = stat.get("email_account_id")
                from_em = stat.get("from_email", "")
                norm_em = normalize_email(from_em)
                key = MailboxKey(
                    smartlead_id=int(acc_id) if acc_id else None,
                    normalized_email=norm_em,
                )
                if key not in mailbox_map:
                    mailbox_map[key] = MailboxAggregate(
                        email=from_em,
                        normalized_email=norm_em,
                        smartlead_email_account_id=key.smartlead_id,
                        from_name=None,
                        client_id=client_id,
                        client_name=client_name,
                    )
                    s_count = int(stat.get("sent_count", 0) or 0)
                    b_count = int(stat.get("bounce_count", 0) or 0)
                    mailbox_map[key].add_direct_stats(campaign_id, s_count, b_count)

        else:
            # FALLBACK ATTRIBUTION (equal-share estimate if direct endpoint not available)
            num_mailboxes = len(email_accounts)
            for account in email_accounts:
                key = MailboxKey.from_account(account)
                email = account.get("from_email", "") or account.get("email", "")

                if key not in mailbox_map:
                    mailbox_map[key] = MailboxAggregate(
                        email=email,
                        normalized_email=key.normalized_email,
                        smartlead_email_account_id=key.smartlead_id,
                        from_name=account.get("from_name"),
                        client_id=client_id,
                        client_name=client_name,
                    )

                mailbox_map[key].add_campaign_stats(
                    campaign_id=campaign_id,
                    campaign_sent=campaign_sent,
                    campaign_bounced=campaign_bounced,
                    num_mailboxes_in_campaign=num_mailboxes,
                )

    aggregates = list(mailbox_map.values())

    multi_mailbox_count = sum(
        1 for a in aggregates if a.has_multi_mailbox_attribution
    )
    if multi_mailbox_count > 0:
        logger.warning(
            "Client %s: %d mailboxes used equal-share attribution "
            "(multi-mailbox campaign). See README § API Limitations.",
            client_name,
            multi_mailbox_count,
        )

    logger.info(
        "Client '%s': aggregated %d unique mailboxes from %d campaigns",
        client_name,
        len(aggregates),
        len(campaign_mailbox_data),
    )

    return aggregates
