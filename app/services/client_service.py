"""
Client service.
Fetches and manages Smartlead client records.
"""
from __future__ import annotations

import logging
from typing import Any

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadError

logger = logging.getLogger(__name__)


def format_client_name(client_data: dict[str, Any]) -> str:
    """Format client name cleanly, combining contact name and company logo if available."""
    name = (client_data.get("name") or "").strip()
    logo = (client_data.get("logo") or "").strip()
    if name and logo and name.lower() != logo.lower():
        return f"{name} ({logo})"
    return name or logo or f"Client {client_data.get('id', 'Unknown')}"


class ClientService:
    def __init__(self, api_client: SmartleadApiClient) -> None:
        self._api = api_client

    async def get_all_clients(self) -> list[dict[str, Any]]:
        """
        Fetch all clients from Smartlead.
        Endpoint: GET /client/ (with fallback: GET /clients).
        """
        try:
            clients = await self._api.get_clients()
            if clients:
                logger.info("Fetched %d clients from Smartlead", len(clients))
                # Ensure each client has a formatted display name
                for c in clients:
                    c["display_name"] = format_client_name(c)
                return clients

            # Non-agency fallback
            logger.info(
                "No clients returned — treating account as single-client."
            )
            return [{"id": 0, "name": "Default Account", "display_name": "Default Account"}]
        except SmartleadError as exc:
            logger.error("Failed to fetch clients: %s", exc)
            return [{"id": 0, "name": "Default Account", "display_name": "Default Account"}]
