"""
Campaign service.
Fetches and caches campaigns from Smartlead.
"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadError

logger = logging.getLogger(__name__)


class CampaignService:
    def __init__(self, api_client: SmartleadApiClient) -> None:
        self._api = api_client

    async def get_campaigns_for_client(
        self, client_id: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch campaigns for a specific client (or all campaigns if client_id is None).
        """
        try:
            campaigns = await self._api.get_campaigns(client_id=client_id)
            logger.info(
                "Fetched %d campaigns%s",
                len(campaigns),
                f" for client {client_id}" if client_id else " (all)",
            )
            return campaigns
        except SmartleadError as exc:
            logger.error("Failed to fetch campaigns: %s", exc)
            return []

    async def get_all_campaigns(self) -> list[dict[str, Any]]:
        """Fetch all campaigns in the account."""
        return await self.get_campaigns_for_client(client_id=None)

