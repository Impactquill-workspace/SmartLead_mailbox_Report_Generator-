"""
Clients API router — proxy endpoints for Smartlead clients.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clients", tags=["Clients"])
_settings = get_settings()


@router.get("/")
async def list_clients() -> list[dict[str, Any]]:
    """List all Smartlead clients."""
    async with SmartleadApiClient(_settings) as client:
        try:
            return await client.get_clients()
        except SmartleadAuthError:
            raise HTTPException(status_code=401, detail="Authentication failed")
        except SmartleadError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
