"""
Analytics service.
Fetches campaign analytics from Smartlead and returns validated totals.
"""
from __future__ import annotations

import logging
from datetime import date

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadError, SmartleadNotFoundError
from app.services.aggregation_service import validate_analytics_data
from app.utils.date_utils import format_date, split_into_30_day_chunks

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, client: SmartleadApiClient) -> None:
        self._api = client

    async def get_campaign_totals(
        self,
        campaign_id: int,
        start_date: date,
        end_date: date,
    ) -> tuple[int, int]:
        """
        Fetch and aggregate analytics for a campaign over the given period.

        Uses official GET /campaigns/{campaign_id}/statistics endpoint to fetch
        accurate sent and bounced totals for the date range.
        Falls back to GET /campaigns/{campaign_id}/analytics-by-date if needed.

        Returns:
            (total_sent, total_bounced) for the full period.
        """
        start_str = format_date(start_date)
        end_str = format_date(end_date)

        try:
            # 1. Fetch total sent count via /statistics
            stats_sent = await self._api.get_campaign_statistics(
                campaign_id=campaign_id,
                start_date=start_str,
                end_date=end_str,
                limit=1,
            )
            raw_sent = stats_sent.get("total_stats", 0)
            total_sent = max(0, int(raw_sent or 0))

            # 2. If sent > 0, fetch bounced count via /statistics with email_status=bounced
            total_bounced = 0
            if total_sent > 0:
                stats_bounced = await self._api.get_campaign_statistics(
                    campaign_id=campaign_id,
                    start_date=start_str,
                    end_date=end_str,
                    email_status="bounced",
                    limit=1,
                )
                raw_bounced = stats_bounced.get("total_stats", 0)
                total_bounced = max(0, int(raw_bounced or 0))

                # Sanity check: bounce cannot exceed sent
                if total_bounced > total_sent:
                    logger.warning(
                        "Campaign %d: bounced (%d) > sent (%d) — capping bounced at sent",
                        campaign_id,
                        total_bounced,
                        total_sent,
                    )
                    total_bounced = total_sent

            logger.debug(
                "Campaign %d: period [%s→%s] total sent=%d bounced=%d (via /statistics)",
                campaign_id,
                start_date,
                end_date,
                total_sent,
                total_bounced,
            )
            return total_sent, total_bounced

        except SmartleadNotFoundError:
            logger.warning(
                "Campaign %d not found during statistics fetch — skipping",
                campaign_id,
            )
            return 0, 0
        except SmartleadError as exc:
            logger.warning(
                "Failed to fetch /statistics for campaign %d [%s→%s]: %s. "
                "Attempting fallback to analytics-by-date.",
                campaign_id,
                start_date,
                end_date,
                exc,
            )
            return await self._fallback_analytics_by_date(campaign_id, start_date, end_date)

    async def _fallback_analytics_by_date(
        self,
        campaign_id: int,
        start_date: date,
        end_date: date,
    ) -> tuple[int, int]:
        """Fallback to /campaigns/{id}/analytics-by-date."""
        chunks = split_into_30_day_chunks(start_date, end_date)
        total_sent = 0
        total_bounced = 0

        for chunk in chunks:
            try:
                daily_data = await self._api.get_campaign_analytics_by_date(
                    campaign_id=campaign_id,
                    start_date=format_date(chunk.start),
                    end_date=format_date(chunk.end),
                )
                chunk_sent, chunk_bounced = validate_analytics_data(
                    daily_data, campaign_id
                )
                total_sent += chunk_sent
                total_bounced += chunk_bounced

            except SmartleadNotFoundError:
                logger.warning(
                    "Campaign %d not found during analytics fetch — skipping",
                    campaign_id,
                )
                return 0, 0
            except SmartleadError as exc:
                logger.error(
                    "Fallback analytics failed for campaign %d [%s→%s]: %s",
                    campaign_id,
                    chunk.start,
                    chunk.end,
                    exc,
                )

        return total_sent, total_bounced
