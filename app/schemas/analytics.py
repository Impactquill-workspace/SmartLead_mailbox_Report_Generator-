"""Pydantic schemas for analytics data from Smartlead API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DailyAnalytics(BaseModel):
    """
    Represents one day of analytics from Smartlead's
    GET /campaigns/{id}/analytics-by-date endpoint.

    IMPORTANT: These are CAMPAIGN-LEVEL counts, not mailbox-level.
    See README.md § Smartlead API Limitations.
    """
    date: str  # YYYY-MM-DD
    sent_count: int = 0
    open_count: int = 0
    click_count: int = 0
    reply_count: int = 0
    bounce_count: int = 0
    unsubscribe_count: int = 0

    @classmethod
    def from_api_response(cls, data: dict) -> "DailyAnalytics":
        """Parse from raw Smartlead API response, tolerating missing fields."""
        return cls(
            date=data.get("date", ""),
            sent_count=int(data.get("sent_count", 0) or 0),
            open_count=int(data.get("open_count", 0) or 0),
            click_count=int(data.get("click_count", 0) or 0),
            reply_count=int(data.get("reply_count", 0) or 0),
            bounce_count=int(data.get("bounce_count", 0) or 0),
            unsubscribe_count=int(data.get("unsubscribe_count", 0) or 0),
        )


class CampaignAnalyticsSummary(BaseModel):
    """Aggregated analytics for one campaign over a date range."""
    campaign_id: int
    total_sent: int = 0
    total_bounced: int = 0
    daily_breakdown: list[DailyAnalytics] = []
