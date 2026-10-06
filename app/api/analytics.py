"""
Analytics API router.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
_settings = get_settings()


@router.get("/overview")
async def global_analytics_overview() -> dict[str, Any]:
    """Fetch global analytics overview across all campaigns."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_global_analytics_overview()
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{campaign_id}/by-date")
async def campaign_analytics_by_date(
    campaign_id: int,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
) -> list[dict[str, Any]]:
    """Fetch campaign analytics for a specific date range."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_campaign_analytics_by_date(
                campaign_id, start_date, end_date
            )
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{campaign_id}/statistics")
async def campaign_statistics(
    campaign_id: int,
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD or ISO)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD or ISO)"),
    email_status: str | None = Query(None, description="opened, clicked, replied, unsubscribed, bounced"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """Fetch campaign email statistics with optional status and date filters."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_campaign_statistics(
                campaign_id=campaign_id,
                start_date=start_date,
                end_date=end_date,
                email_status=email_status,
                offset=offset,
                limit=limit,
            )
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

