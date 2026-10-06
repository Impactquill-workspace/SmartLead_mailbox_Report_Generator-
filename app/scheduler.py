"""
APScheduler configuration for weekly report generation.
Runs every Monday morning (configurable via environment variables).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings

logger = logging.getLogger(__name__)

DAY_OF_WEEK_MAP = {
    "MONDAY": "mon",
    "TUESDAY": "tue",
    "WEDNESDAY": "wed",
    "THURSDAY": "thu",
    "FRIDAY": "fri",
    "SATURDAY": "sat",
    "SUNDAY": "sun",
}


def run_weekly_report_job() -> None:
    """
    Scheduled job: generate the previous calendar week report.
    This runs in a background thread — uses asyncio.run() to execute async code.
    """
    logger.info("=== Scheduled weekly report job triggered ===")
    try:
        from app.clients.smartlead_client import SmartleadApiClient
        from app.core.config import get_settings
        from app.services.weekly_report_service import WeeklyReportService
        from app.utils.date_utils import get_previous_calendar_week

        _settings = get_settings()
        date_range = get_previous_calendar_week()

        async def _run():
            async with SmartleadApiClient(_settings) as api_client:
                service = WeeklyReportService(
                    api_client=api_client,
                    db_session=None,  # No DB in scheduled job (no async session in thread)
                    dry_run=_settings.dry_run,
                )
                report = await service.generate_report(date_range.start, date_range.end)
                logger.info(
                    "Scheduled report done: %d clients, %d mailboxes, "
                    "sent=%d, bounced=%d",
                    report.total_clients,
                    report.total_mailboxes,
                    report.total_sent,
                    report.total_bounced,
                )

        asyncio.run(_run())

    except Exception as exc:
        logger.error("Scheduled report job failed: %s", exc, exc_info=True)


def create_scheduler(settings: Settings) -> Optional[BackgroundScheduler]:
    """
    Create and configure the APScheduler instance.

    Returns None if the report day configuration is invalid.
    """
    day_of_week = settings.report_day.upper()
    cron_day = DAY_OF_WEEK_MAP.get(day_of_week)

    if not cron_day:
        logger.warning(
            "Invalid REPORT_DAY=%s — scheduler not started. "
            "Valid values: %s",
            settings.report_day,
            ", ".join(DAY_OF_WEEK_MAP.keys()),
        )
        return None

    scheduler = BackgroundScheduler(timezone="UTC")
    trigger = CronTrigger(
        day_of_week=cron_day,
        hour=settings.report_hour,
        minute=settings.report_minute,
    )
    scheduler.add_job(
        func=run_weekly_report_job,
        trigger=trigger,
        id="weekly_report",
        name="Weekly Mailbox Report",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace period if server was down
    )

    return scheduler
