"""
Campaigns API router.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])
_settings = get_settings()


@router.get("/")
async def list_campaigns(
    client_id: Optional[int] = Query(None, description="Filter by client ID")
) -> list[dict[str, Any]]:
    """List all campaigns, optionally filtered by client_id."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_campaigns(client_id=client_id)
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{campaign_id}/email-accounts")
async def get_campaign_email_accounts(campaign_id: int) -> list[dict[str, Any]]:
    """Get all email accounts attached to a campaign."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_campaign_email_accounts(campaign_id)
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
