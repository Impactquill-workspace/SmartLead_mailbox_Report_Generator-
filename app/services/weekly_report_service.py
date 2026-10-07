"""
Weekly Report Service — Main orchestrator.

Implements the full data collection and aggregation pipeline:

1.  Calculate date range (previous calendar week or custom)
2.  Fetch all Smartlead clients
3.  For each client: fetch campaigns
4.  For each campaign: fetch email accounts (mailboxes)
5.  Build unique mailbox registry (deduplicated)
6.  For each campaign: fetch analytics for the date range
7.  Aggregate stats at mailbox level (see aggregation_service.py)
8.  Validate data integrity
9.  Persist to PostgreSQL
10. Generate Excel report
11. Return report summary

DATA ATTRIBUTION NOTE:
Analytics from Smartlead are campaign-level, not mailbox-level.
When a campaign has multiple mailboxes, equal-share attribution is used.
This limitation is clearly documented in the report output.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
from app.services.aggregation_service import MailboxAggregate, aggregate_mailboxes
from app.services.analytics_service import AnalyticsService
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService
from app.services.mailbox_service import MailboxService
from app.models.client import Client
from app.models.campaign import Campaign
from app.models.mailbox import Mailbox
from app.models.campaign_mailbox import CampaignMailbox
from app.models.mailbox_stat import MailboxStat
from app.models.report import Report
from app.schemas.report import ClientReportItem, MailboxReportItem, WeeklyReportResponse
from app.utils.date_utils import (
    DateRange,
    format_date,
    get_previous_calendar_week,
    parse_date,
)
from app.utils.email_utils import normalize_email
from app.utils.export_utils import generate_excel_report

logger = logging.getLogger(__name__)

DATA_ATTRIBUTION_NOTE = (
    "Mailbox delivery statistics are fetched directly from Smartlead's official "
    "Email Health Metrics endpoint (GET /analytics/mailbox/name-wise-health-metrics), "
    "providing exact Leads Contacted, Total Sent, Bounces, and Bounce Rate for each individual sending mailbox."
)


class WeeklyReportService:
    """
    Orchestrates the full weekly report generation pipeline.
    """

    def __init__(
        self,
        api_client: SmartleadApiClient,
        db_session: AsyncSession | None = None,
        dry_run: bool = False,
    ) -> None:
        self._api = api_client
        self._db = db_session
        self._dry_run = dry_run
        self._client_service = ClientService(api_client)
        self._campaign_service = CampaignService(api_client)
        self._mailbox_service = MailboxService(api_client)
        self._analytics_service = AnalyticsService(api_client)

    async def generate_previous_week_report(
        self,
        status_filter: Optional[str] = None,
    ) -> WeeklyReportResponse:
        """Generate report for the previous calendar week (Mon–Sun)."""
        date_range = get_previous_calendar_week()
        logger.info(
            "Generating previous week report: %s -> %s",
            date_range.start,
            date_range.end,
        )
        return await self.generate_report(date_range.start, date_range.end, status_filter=status_filter)

    async def generate_report(
        self,
        start_date: date,
        end_date: date,
        status_filter: Optional[str] = None,
        client_id_filter: Optional[int] = None,
    ) -> WeeklyReportResponse:
        """
        Generate the full mailbox report for the given date range.

        Args:
            start_date: Inclusive report start date.
            end_date: Inclusive report end date.
            status_filter: Optional campaign status filter (e.g. 'ACTIVE').
            client_id_filter: Optional client ID filter to run for a specific client.

        Returns:
            WeeklyReportResponse with all client/mailbox data.
        """
        logger.info(
            "=== Report generation started: %s -> %s (status_filter: %s, client_id_filter: %s) ===",
            start_date,
            end_date,
            status_filter or "ALL",
            client_id_filter or "ALL",
        )

        if self._dry_run:
            logger.info("DRY RUN mode: data will be read but NOT saved to Smartlead")

        # Step 1: Fetch all clients from Smartlead
        raw_clients = await self._client_service.get_all_clients()
        logger.info("Clients fetched: %d", len(raw_clients))
        client_map: dict[int, dict[str, Any]] = {c.get("id", 0): c for c in raw_clients}

        # Step 2: Fetch all campaigns once from Smartlead
        all_campaigns = await self._campaign_service.get_all_campaigns()
        logger.info("Total campaigns fetched: %d", len(all_campaigns))

        include_archived = getattr(self._api._settings, "smartlead_include_archived", False)
        include_drafted = getattr(self._api._settings, "smartlead_include_drafted", False)

        # Group campaigns by client_id
        campaigns_by_client: dict[int, list[dict[str, Any]]] = {}
        skipped_archived = 0
        skipped_drafted = 0
        skipped_status = 0
        for c in all_campaigns:
            c_client_id = c.get("client_id") or 0
            if client_id_filter is not None and c_client_id != client_id_filter:
                continue

            c_status = str(c.get("status", "")).upper()
            if status_filter and c_status != status_filter.upper():
                skipped_status += 1
                continue
            if c_status == "DRAFTED" and not include_drafted:
                skipped_drafted += 1
                continue
            if c_status == "ARCHIVED" and not include_archived:
                skipped_archived += 1
                continue
            campaigns_by_client.setdefault(c_client_id, []).append(c)

        # Ensure single client is queried even if they have 0 campaigns returned by listing
        if client_id_filter is not None and client_id_filter not in campaigns_by_client:
            campaigns_by_client[client_id_filter] = []

        if skipped_status > 0:
            logger.info("Campaign status filter '%s': skipped %d non-matching campaigns.", status_filter, skipped_status)

        if skipped_archived > 0 or skipped_drafted > 0:
            logger.info(
                "Campaign filter: skipped %d ARCHIVED, %d DRAFTED. Processing across %d clients/buckets.",
                skipped_archived,
                skipped_drafted,
                len(campaigns_by_client),
            )

        # Step 2.5: Build global mailbox email -> account mapping
        all_accounts = await self._mailbox_service.get_all_mailboxes()
        email_to_id: dict[str, int] = {}
        email_to_name: dict[str, str] = {}
        for acc in all_accounts:
            acc_id = acc.get("id")
            norm_em = normalize_email(acc.get("from_email", "") or acc.get("email", ""))
            if acc_id and norm_em:
                email_to_id[norm_em] = int(acc_id)
            if norm_em and acc.get("from_name"):
                email_to_name[norm_em] = acc.get("from_name")

        client_report_items: list[ClientReportItem] = []
        all_aggregates: list[MailboxAggregate] = []

        concurrency = getattr(self._api._settings, "smartlead_max_concurrency", 5)
        sem = asyncio.Semaphore(concurrency)

        start_str = format_date(start_date)
        end_str = format_date(end_date)

        # Step 3: Process each client
        async def process_single_client(
            client_sl_id: int,
            campaigns: list[dict[str, Any]],
        ) -> tuple[ClientReportItem | None, list[MailboxAggregate]]:
            client_info = client_map.get(client_sl_id, {})
            client_name = client_info.get("display_name") or client_info.get("name")
            if not client_name:
                client_name = f"Client {client_sl_id}" if client_sl_id != 0 else "Internal / Direct Account"

            logger.info("Processing client: %s (id=%s, %d campaigns)", client_name, client_sl_id, len(campaigns))

            client_camp_ids = [c["id"] for c in campaigns if c.get("id")]
            client_id_param = str(client_sl_id) if client_sl_id != 0 else None
            camp_ids_param = ",".join(map(str, client_camp_ids)) if client_camp_ids else None

            # Primary approach: Official Smartlead Email Health Metrics
            health_metrics: list[dict[str, Any]] = []
            async with sem:
                try:
                    health_metrics = await self._api.get_mailbox_health_metrics(
                        start_date=start_str,
                        end_date=end_str,
                        client_ids=client_id_param,
                        campaign_ids=camp_ids_param,
                        full_data=True,
                    )
                except Exception as exc:
                    logger.debug("Health metrics endpoint error for client %s: %s", client_sl_id, exc)

            if health_metrics:
                aggregates: list[MailboxAggregate] = []
                for item in health_metrics:
                    email = item.get("from_email", "")
                    if not email:
                        continue
                    norm_em = normalize_email(email)
                    sent = int(item.get("sent", 0) or 0)
                    bounced = int(item.get("bounced", 0) or 0)
                    leads = int(item.get("unique_lead_count", 0) or 0)

                    raw_rate = item.get("bounce_rate")
                    b_rate = None
                    if isinstance(raw_rate, str) and "%" in raw_rate:
                        try:
                            b_rate = round(float(raw_rate.replace("%", "").strip()), 2)
                        except ValueError:
                            pass
                    elif isinstance(raw_rate, (int, float)):
                        b_rate = round(float(raw_rate), 2)

                    agg = MailboxAggregate(
                        email=email,
                        normalized_email=norm_em,
                        smartlead_email_account_id=email_to_id.get(norm_em),
                        from_name=email_to_name.get(norm_em),
                        client_id=client_sl_id,
                        client_name=client_name,
                        sent=sent,
                        bounced=bounced,
                        leads_contacted=leads,
                        custom_bounce_rate=b_rate,
                    )
                    aggregates.append(agg)

                aggregates.sort(key=lambda a: (-a.sent, a.email))
                mailbox_items = [
                    MailboxReportItem(
                        email=agg.email,
                        mailbox_id=agg.smartlead_email_account_id,
                        leads_contacted=agg.leads_contacted,
                        sent=agg.sent,
                        bounced=agg.bounced,
                        bounce_rate=agg.bounce_rate,
                    )
                    for agg in aggregates
                ]
                client_item = (
                    ClientReportItem(
                        client_id=client_sl_id,
                        client_name=client_name,
                        mailboxes=mailbox_items,
                    )
                    if mailbox_items
                    else None
                )
                return client_item, aggregates

            # Fallback approach: Campaign-by-campaign mailbox statistics
            total_camps = len(campaigns)

            async def process_campaign(campaign: dict[str, Any], idx: int) -> dict[str, Any] | None:
                campaign_id = campaign.get("id")
                campaign_name = campaign.get("name", f"Campaign {campaign_id}")
                campaign_status = campaign.get("status", "UNKNOWN")
                if not campaign_id:
                    return None

                async with sem:
                    mailbox_stats = await self._api.get_campaign_mailbox_statistics(
                        campaign_id=campaign_id,
                        start_date=start_str,
                        end_date=end_str,
                    )
                    email_accounts = await self._mailbox_service.get_campaign_mailboxes(campaign_id)
                    total_sent = sum(m.get("sent_count", 0) for m in mailbox_stats)
                    total_bounced = sum(m.get("bounce_count", 0) for m in mailbox_stats)
                    unique_sent_count = 0
                    if total_sent > 0:
                        camp_analytics = await self._api.get_campaign_date_analytics(
                            campaign_id=campaign_id,
                            start_date=start_str,
                            end_date=end_str,
                        )
                        unique_sent_count = int(camp_analytics.get("unique_sent_count", 0) or 0)

                    return {
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "total_sent": total_sent,
                        "total_bounced": total_bounced,
                        "unique_sent_count": unique_sent_count,
                        "mailbox_stats": mailbox_stats,
                        "email_accounts": email_accounts,
                    }

            c_results = await asyncio.gather(
                *(process_campaign(c, idx) for idx, c in enumerate(campaigns, 1)),
                return_exceptions=True,
            )
            campaign_mailbox_data: list[dict[str, Any]] = []
            for res in c_results:
                if isinstance(res, Exception):
                    logger.error("Campaign processing error: %s", res)
                elif res is not None:
                    campaign_mailbox_data.append(res)

            aggregates = aggregate_mailboxes(
                client_id=client_sl_id,
                client_name=client_name,
                campaign_mailbox_data=campaign_mailbox_data,
            )
            aggregates.sort(key=lambda a: (-a.sent, a.email))
            mailbox_items = [
                MailboxReportItem(
                    email=agg.email,
                    mailbox_id=agg.smartlead_email_account_id,
                    leads_contacted=agg.leads_contacted,
                    sent=agg.sent,
                    bounced=agg.bounced,
                    bounce_rate=agg.bounce_rate,
                )
                for agg in aggregates
            ]
            client_item = (
                ClientReportItem(
                    client_id=client_sl_id,
                    client_name=client_name,
                    mailboxes=mailbox_items,
                )
                if mailbox_items
                else None
            )
            return client_item, aggregates

        client_tasks = [
            process_single_client(c_id, camps)
            for c_id, camps in campaigns_by_client.items()
        ]
        client_outcomes = await asyncio.gather(*client_tasks, return_exceptions=True)

        for outcome in client_outcomes:
            if isinstance(outcome, Exception):
                logger.error("Error processing client: %s", outcome)
            elif outcome:
                c_item, aggs = outcome
                if c_item and c_item.mailboxes:
                    client_report_items.append(c_item)
                all_aggregates.extend(aggs)

        # Sort clients alphabetically by name
        client_report_items.sort(key=lambda c: c.client_name.lower())

        # Step 8: Summary totals
        total_mailboxes = sum(len(c.mailboxes) for c in client_report_items)
        total_leads_contacted = sum(c.total_leads_contacted for c in client_report_items)
        total_sent = sum(
            sum(m.sent for m in c.mailboxes) for c in client_report_items
        )
        total_bounced = sum(
            sum(m.bounced for m in c.mailboxes) for c in client_report_items
        )
        overall_bounce_rate = (
            round((total_bounced / total_sent) * 100, 2) if total_sent > 0 else 0.0
        )

        logger.info(
            "=== Report summary: %d clients, %d mailboxes, "
            "leads=%d, sent=%d, bounced=%d, bounce_rate=%.2f%% ===",
            len(client_report_items),
            total_mailboxes,
            total_leads_contacted,
            total_sent,
            total_bounced,
            overall_bounce_rate,
        )

        response = WeeklyReportResponse(
            period_start=format_date(start_date),
            period_end=format_date(end_date),
            generated_at=datetime.now().isoformat(),
            total_clients=len(client_report_items),
            total_mailboxes=total_mailboxes,
            total_leads_contacted=total_leads_contacted,
            total_sent=total_sent,
            total_bounced=total_bounced,
            overall_bounce_rate=overall_bounce_rate,
            data_attribution_note=DATA_ATTRIBUTION_NOTE,
            clients=client_report_items,
        )

        # Step 9: Persist to DB (if session provided and not dry run)
        if self._db and not self._dry_run:
            await self._persist_report(response, all_aggregates)

        # Step 10: Generate Excel
        report_data = {
            "clients": [
                {
                    "client_id": c.client_id,
                    "client_name": c.client_name,
                    "mailboxes": [
                        {
                            "email": m.email,
                            "mailbox_id": m.mailbox_id,
                            "leads_contacted": m.leads_contacted,
                            "sent": m.sent,
                            "bounced": m.bounced,
                            "bounce_rate": m.bounce_rate,
                        }
                        for m in c.mailboxes
                    ],
                }
                for c in client_report_items
            ],
            "data_attribution_note": DATA_ATTRIBUTION_NOTE,
        }

        try:
            excel_path = generate_excel_report(
                report_data=report_data,
                period_start=start_date,
                period_end=end_date,
            )
            response.excel_file_path = str(excel_path)
            logger.info("Excel report: %s", excel_path)
        except Exception as exc:
            logger.error("Excel generation failed: %s", exc)

        return response

    async def _persist_report(
        self,
        response: WeeklyReportResponse,
        aggregates: list[MailboxAggregate],
    ) -> None:
        """Persist report metadata and mailbox stats to PostgreSQL."""
        if not self._db:
            return

        logger.info("Persisting report to database")

        try:
            start_date = parse_date(response.period_start)
            end_date = parse_date(response.period_end)

            # Upsert clients and mailboxes, then save stats
            for agg in aggregates:
                await self._upsert_mailbox_stat(agg, start_date, end_date)

            # Save report record
            report_record = Report(
                period_start=start_date,
                period_end=end_date,
                total_clients=response.total_clients,
                total_mailboxes=response.total_mailboxes,
                total_sent=response.total_sent,
                total_bounced=response.total_bounced,
                overall_bounce_rate=response.overall_bounce_rate,
            )
            self._db.add(report_record)
            await self._db.commit()
            logger.info("Report persisted to database")

        except Exception as exc:
            logger.error("Failed to persist report: %s", exc)
            await self._db.rollback()

    async def _upsert_mailbox_stat(
        self,
        agg: MailboxAggregate,
        start_date: date,
        end_date: date,
    ) -> None:
        """Insert or update a MailboxStat row."""
        if not self._db:
            return

        # Find or create the mailbox record
        stmt = select(Mailbox)
        if agg.smartlead_email_account_id:
            stmt = stmt.where(
                Mailbox.smartlead_email_account_id == agg.smartlead_email_account_id
            )
        else:
            stmt = stmt.where(Mailbox.normalized_email == agg.normalized_email)

        result = await self._db.execute(stmt)
        mailbox = result.scalar_one_or_none()

        if not mailbox:
            mailbox = Mailbox(
                smartlead_email_account_id=agg.smartlead_email_account_id,
                email=agg.email,
                normalized_email=agg.normalized_email,
                from_name=agg.from_name,
            )
            self._db.add(mailbox)
            await self._db.flush()

        # Find or create MailboxStat
        stat_stmt = select(MailboxStat).where(
            MailboxStat.mailbox_id == mailbox.id,
            MailboxStat.period_start == start_date,
            MailboxStat.period_end == end_date,
        )
        stat_result = await self._db.execute(stat_stmt)
        stat = stat_result.scalar_one_or_none()

        if stat:
            stat.sent = agg.sent
            stat.bounced = agg.bounced
            stat.bounce_rate = agg.bounce_rate
        else:
            stat = MailboxStat(
                mailbox_id=mailbox.id,
                period_start=start_date,
                period_end=end_date,
                sent=agg.sent,
                bounced=agg.bounced,
                bounce_rate=agg.bounce_rate,
            )
            self._db.add(stat)
