"""
Mailbox service.
Fetches email accounts for campaigns and builds the mailbox registry.
"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadError

logger = logging.getLogger(__name__)


class MailboxService:
    def __init__(self, api_client: SmartleadApiClient) -> None:
        self._api = api_client

    async def get_campaign_mailboxes(
        self, campaign_id: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all email accounts (mailboxes) attached to a campaign.

        Returns a list of email account dicts from Smartlead:
        [{"id": int, "from_email": str, "from_name": str, ...}]
        """
        try:
            accounts = await self._api.get_campaign_email_accounts(campaign_id)
            logger.debug(
                "Campaign %d: found %d email accounts", campaign_id, len(accounts)
            )
            return accounts
        except SmartleadError as exc:
            logger.error(
                "Failed to fetch email accounts for campaign %d: %s",
                campaign_id,
                exc,
            )
            return []
