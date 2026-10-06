"""
Report service — handles report storage and retrieval from PostgreSQL.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_latest_report(self) -> Optional[Report]:
        """Get the most recently generated report."""
        stmt = select(Report).order_by(Report.generated_at.desc()).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_report_by_period(
        self, start_date: date, end_date: date
    ) -> Optional[Report]:
        """Get a report for a specific period."""
        stmt = select(Report).where(
            Report.period_start == start_date,
            Report.period_end == end_date,
        ).order_by(Report.generated_at.desc()).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reports(self, limit: int = 20) -> list[Report]:
        """List recent reports."""
        stmt = select(Report).order_by(Report.generated_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
