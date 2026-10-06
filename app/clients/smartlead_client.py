"""
Smartlead API client.

Authentication: API key passed as ?api_key= query parameter (no Bearer token).
Base URL: https://server.smartlead.ai/api/v1

Rate limits: 10 requests / 2 seconds — controlled with asyncio.Semaphore.
Retry logic: exponential backoff for transient errors (429, 5xx, network).
Auth errors (401, 403) are raised immediately and NOT retried.

SECURITY: The API key is NEVER logged. Only safe/masked versions appear in logs.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.clients.smartlead_exceptions import (
    SmartleadAuthError,
    SmartleadError,
    SmartleadNetworkError,
    SmartleadNotFoundError,
    SmartleadRateLimitError,
    SmartleadServerError,
    SmartleadValidationError,
)
from app.core.config import Settings
from app.core.security import sanitize_url_for_logging

logger = logging.getLogger(__name__)


class SmartleadApiClient:
    """
    Async HTTP client for the Smartlead API v1.

    Usage:
        async with SmartleadApiClient(settings) as client:
            campaigns = await client.get_campaigns()

    Or manage lifecycle manually:
        client = SmartleadApiClient(settings)
        await client.open()
        ...
        await client.close()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # SECURITY: API key stored privately — never passed to __repr__
        self._api_key = settings.smartlead_api_key
        self._base_url = settings.api_base_url.rstrip("/")
        self._timeout = httpx.Timeout(settings.smartlead_request_timeout)
        self._max_retries = max(settings.smartlead_max_retries, 3)
        self._semaphore = asyncio.Semaphore(settings.smartlead_max_concurrency)
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time: float = 0.0
        self._cooldown_until: float = 0.0
        self._min_request_interval: float = getattr(settings, "smartlead_request_interval", 0.35)
        self._max_retry_delay: float = getattr(settings, "smartlead_max_retry_delay", 65.0)

    async def open(self) -> None:
        """Open the underlying HTTP connection pool."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "SmartleadApiClient":
        await self.open()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    #  Private helpers
    # ------------------------------------------------------------------ #

    def _build_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build query parameters, always injecting the API key."""
        params: dict[str, Any] = {"api_key": self._api_key}
        if extra:
            params.update(extra)
        return params

    def _safe_url(self, url: str) -> str:
        """Strip API key from a URL string for safe logging."""
        return sanitize_url_for_logging(url)

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute a GET request with retry logic.

        Retryable:   429, 5xx, network errors
        Not retried: 401, 403 (auth failure)
        """
        if self._client is None:
            await self.open()

        url = f"{self._base_url}/{path.lstrip('/')}"
        query_params = self._build_params(params)

        async def _acquire_pacing() -> None:
            """Ensure minimum delay between requests and pause if global cooldown is active."""
            async with self._rate_limit_lock:
                loop = asyncio.get_running_loop()
                now = loop.time()

                # If global cooldown from a previous 429 is active, wait it out
                if now < self._cooldown_until:
                    wait_secs = min(self._cooldown_until - now, self._max_retry_delay)
                    if wait_secs > 0:
                        logger.warning(
                            "Rate limit cooldown active. Pausing requests for %.1f seconds...",
                            wait_secs,
                        )
                        await asyncio.sleep(wait_secs)
                        now = loop.time()

                # Enforce minimum interval between all outgoing requests
                elapsed = now - self._last_request_time
                if elapsed < self._min_request_interval:
                    await asyncio.sleep(self._min_request_interval - elapsed)
                self._last_request_time = loop.time()

        async def _attempt() -> Any:
            async with self._semaphore:
                await _acquire_pacing()
                safe_url = self._safe_url(f"{url}?api_key=****")
                logger.debug("GET %s", safe_url)
                try:
                    response = await self._client.get(url, params=query_params)  # type: ignore[union-attr]
                except httpx.TimeoutException as exc:
                    raise SmartleadNetworkError(
                        f"Request timed out: {safe_url}"
                    ) from exc
                except httpx.ConnectError as exc:
                    raise SmartleadNetworkError(
                        f"Connection error: {safe_url}"
                    ) from exc
                except httpx.RequestError as exc:
                    raise SmartleadNetworkError(
                        f"Network error for {safe_url}: {exc}"
                    ) from exc

                return self._handle_response(response, safe_url)

        def _custom_wait(retry_state: RetryCallState) -> float:
            """Custom wait: obey Retry-After for 429, otherwise exponential."""
            if retry_state.outcome and retry_state.outcome.failed:
                exc = retry_state.outcome.exception()
                if isinstance(exc, SmartleadRateLimitError) and exc.retry_after:
                    wait_time = float(exc.retry_after) + 2.0
                    return min(wait_time, self._max_retry_delay)
            exp = min(1.0 * (2 ** (retry_state.attempt_number - 1)), 30.0)
            return min(exp, self._max_retry_delay)

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(
                (SmartleadRateLimitError, SmartleadServerError, SmartleadNetworkError)
            ),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=_custom_wait,
            reraise=True,
        ):
            with attempt:
                return await _attempt()

    def _handle_response(self, response: httpx.Response, safe_url: str) -> Any:
        """Parse response or raise appropriate exception."""
        status = response.status_code

        if status == 200:
            try:
                return response.json()
            except Exception as exc:
                raise SmartleadValidationError(
                    f"Invalid JSON from {safe_url}: {exc}"
                ) from exc

        if status in (401, 403):
            raise SmartleadAuthError(
                f"Authentication failed ({status}) for {safe_url}. "
                "Check SMARTLEAD_API_KEY in your .env file.",
                status_code=status,
            )

        if status == 404:
            raise SmartleadNotFoundError(
                f"Resource not found ({status}): {safe_url}",
                status_code=status,
            )

        if status == 429:
            retry_after: float = 60.0
            ra_header = response.headers.get("Retry-After")
            if ra_header:
                try:
                    retry_after = float(ra_header)
                except ValueError:
                    pass
            loop = asyncio.get_running_loop()
            self._cooldown_until = loop.time() + retry_after + 2.0
            logger.warning(
                "Rate limit hit for %s. Retry-After: %.1f. Setting global cooldown for %.1fs.",
                safe_url,
                retry_after,
                retry_after + 2.0,
            )
            raise SmartleadRateLimitError(
                f"Rate limit exceeded for {safe_url}",
                retry_after=retry_after,
            )

        if status >= 500:
            raise SmartleadServerError(
                f"Server error ({status}) for {safe_url}: {response.text[:200]}",
                status_code=status,
            )

        # Any other unexpected status
        raise SmartleadError(
            f"Unexpected HTTP status {status} for {safe_url}",
            status_code=status,
        )

    # ------------------------------------------------------------------ #
    #  Public API methods
    # ------------------------------------------------------------------ #

    async def get_clients(self) -> list[dict[str, Any]]:
        """
        Fetch all clients for agency/white-label accounts.
        Endpoint: GET /client/ (fallback: GET /clients)
        Returns list of client objects with id, name, logo, etc.
        """
        logger.info("Fetching all clients from Smartlead")
        for endpoint in ("/client/", "/clients"):
            try:
                result = await self._get(endpoint)
                if isinstance(result, list):
                    return result
                if isinstance(result, dict):
                    return result.get("data", result.get("clients", []))
            except SmartleadNotFoundError:
                continue
            except SmartleadError as exc:
                logger.warning("Error fetching %s: %s", endpoint, exc)
                continue

        logger.warning(
            "Client endpoints returned 404 or empty. Falling back to empty client list."
        )
        return []

    async def get_campaigns(
        self,
        client_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all campaigns, optionally filtered by client_id.
        Endpoint: GET /campaigns/
        """
        params: dict[str, Any] = {}
        if client_id is not None:
            params["client_id"] = client_id

        logger.info(
            "Fetching campaigns%s",
            f" for client_id={client_id}" if client_id else " (all)",
        )
        result = await self._get("/campaigns/", params=params)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", [])
        return []

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        """
        Fetch a single campaign by ID.
        Endpoint: GET /campaigns/{campaign_id}
        """
        logger.debug("Fetching campaign %d", campaign_id)
        result = await self._get(f"/campaigns/{campaign_id}")
        if isinstance(result, dict):
            return result
        raise SmartleadValidationError(
            f"Unexpected response type for campaign {campaign_id}: {type(result)}"
        )

    async def get_campaign_email_accounts(
        self,
        campaign_id: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch all email accounts (mailboxes) attached to a campaign.
        Endpoint: GET /campaigns/{campaign_id}/email-accounts

        Response includes: id (email_account_id), from_email, from_name,
        smtp/imap config, daily limits, auth status.
        """
        logger.debug("Fetching email accounts for campaign %d", campaign_id)
        try:
            result = await self._get(f"/campaigns/{campaign_id}/email-accounts")
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                return result.get("data", result.get("email_accounts", []))
            return []
        except SmartleadNotFoundError:
            logger.warning(
                "Campaign %d not found when fetching email accounts", campaign_id
            )
            return []

    async def get_campaign_mailbox_statistics(
        self,
        campaign_id: int,
        start_date: str,
        end_date: str,
        time_zone: str = "UTC",
    ) -> list[dict[str, Any]]:
        """
        Fetch mailbox statistics specific to a campaign for a date range.
        Endpoint: GET /campaigns/{campaign_id}/mailbox-statistics

        Official documentation: https://api.smartlead.ai/api-reference/campaign-statistics/mailbox-statistics
        Paginates automatically (limit max 20 per page).

        Returns list of mailbox stat records:
          [
            {
              "email_account_id": int,
              "from_email": str,
              "sent_count": int,
              "bounce_count": int,
              "sender_bounce_count": int,
              ...
            }
          ]
        """
        all_stats: list[dict[str, Any]] = []
        offset = 0
        limit = 20

        while True:
            params: dict[str, Any] = {
                "start_date": start_date,
                "end_date": end_date,
                "time_zone": time_zone,
                "offset": offset,
                "limit": limit,
            }
            try:
                result = await self._get(
                    f"/campaigns/{campaign_id}/mailbox-statistics",
                    params=params,
                )
            except SmartleadNotFoundError:
                logger.debug("Campaign %d not found in mailbox-statistics", campaign_id)
                break

            if isinstance(result, dict):
                data = result.get("data", [])
            elif isinstance(result, list):
                data = result
            else:
                data = []

            if not data:
                break

            all_stats.extend(data)
            if len(data) < limit:
                break
            offset += limit

        return all_stats

    async def get_campaign_analytics_by_date(
        self,
        campaign_id: int,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch per-day analytics for a campaign within a date range.
        Endpoint: GET /campaigns/{campaign_id}/analytics-by-date

        IMPORTANT LIMITATION (documented):
        This endpoint returns CAMPAIGN-LEVEL daily aggregates, not mailbox-level.
        Fields returned per day: sent_count, open_count, click_count,
        reply_count, bounce_count, unsubscribe_count, date.

        Maximum date span: 30 days (enforced by Smartlead).

        See README.md § "Smartlead API Limitations" for the full explanation
        of why direct mailbox-level historical attribution is not available
        from this endpoint.
        """
        logger.debug(
            "Fetching analytics for campaign %d [%s → %s]",
            campaign_id,
            start_date,
            end_date,
        )
        try:
            result = await self._get(
                f"/campaigns/{campaign_id}/analytics-by-date",
                params={"start_date": start_date, "end_date": end_date},
            )
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                if "data" in result and isinstance(result["data"], list):
                    return result["data"]
                return [result]
            return []
        except SmartleadNotFoundError:
            logger.warning(
                "Campaign %d not found when fetching analytics", campaign_id
            )
            return []

    async def get_campaign_date_analytics(
        self,
        campaign_id: int,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        Fetch summary analytics (including unique_sent_count / unique leads contacted)
        for a campaign within a date range.
        Endpoint: GET /campaigns/{campaign_id}/analytics-by-date
        """
        logger.debug(
            "Fetching summary analytics for campaign %d [%s → %s]",
            campaign_id,
            start_date,
            end_date,
        )
        try:
            result = await self._get(
                f"/campaigns/{campaign_id}/analytics-by-date",
                params={"start_date": start_date, "end_date": end_date},
            )
            if isinstance(result, dict):
                return result
            if isinstance(result, list) and result:
                return result[0]
            return {}
        except (SmartleadNotFoundError, SmartleadError) as exc:
            logger.debug(
                "Campaign %d analytics-by-date error: %s", campaign_id, exc
            )
            return {}

    async def get_campaign_statistics(
        self,
        campaign_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
        email_status: str | None = None,
        sequence_number: int | None = None,
        offset: int = 0,
        limit: int = 1,
    ) -> dict[str, Any]:
        """
        Fetch campaign email statistics (total_stats count and data records).
        Endpoint: GET /campaigns/{campaign_id}/statistics

        Official documentation: https://api.smartlead.ai/api-reference/campaigns/statistics
        Supports filtering by:
          - sent_time_start_date (ISO format or YYYY-MM-DD)
          - sent_time_end_date (ISO format or YYYY-MM-DD)
          - email_status: opened, clicked, replied, unsubscribed, bounced
          - email_sequence_number: 1..20
          - offset: pagination offset (default 0)
          - limit: page size (default 1, max 1000)

        Returns:
          Dict containing 'total_stats' (int or str) and 'data' (list).
        """
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
        }
        if start_date:
            params["sent_time_start_date"] = start_date
        if end_date:
            params["sent_time_end_date"] = end_date
        if email_status:
            params["email_status"] = email_status
        if sequence_number is not None:
            params["email_sequence_number"] = sequence_number

        logger.debug(
            "Fetching statistics for campaign %d [%s → %s, status=%s, limit=%d]",
            campaign_id,
            start_date,
            end_date,
            email_status,
            limit,
        )
        try:
            result = await self._get(
                f"/campaigns/{campaign_id}/statistics",
                params=params,
            )
            if isinstance(result, dict):
                return result
            return {"total_stats": 0, "data": []}
        except SmartleadNotFoundError:
            logger.warning(
                "Campaign %d not found when fetching statistics", campaign_id
            )
            return {"total_stats": 0, "data": []}

    async def get_campaign_analytics(
        self,
        campaign_id: int,
    ) -> dict[str, Any]:
        """
        Fetch top-level aggregate analytics for a campaign.
        Endpoint: GET /campaigns/{campaign_id}/analytics

        Returns total sent, opens, clicks, replies, lead status distribution,
        and client information.
        """
        logger.debug("Fetching aggregate analytics for campaign %d", campaign_id)
        try:
            result = await self._get(f"/campaigns/{campaign_id}/analytics")
            if isinstance(result, dict):
                return result
            return {}
        except SmartleadNotFoundError:
            logger.warning(
                "Campaign %d not found when fetching aggregate analytics", campaign_id
            )
            return {}

    async def get_global_analytics_overview(self) -> dict[str, Any]:
        """
        Fetch global analytics across all campaigns.
        Endpoint: GET /analytics/overview

        Per the official docs, this includes:
        'email health by domain and individual account (with bounce rate)'

        NOTE: This endpoint returns aggregate totals, not date-range filtered data.
        It is used as a supplementary data source.
        """
        logger.info("Fetching global analytics overview")
        try:
            result = await self._get("/analytics/overview")
            if isinstance(result, dict):
                return result
            return {}
        except SmartleadNotFoundError:
            logger.warning("/analytics/overview endpoint returned 404")
            return {}

    async def get_email_accounts(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch all email accounts for the authenticated user.
        Endpoint: GET /email-accounts/
        Supports pagination via offset/limit.
        """
        logger.debug("Fetching email accounts (offset=%d, limit=%d)", offset, limit)
        result = await self._get(
            "/email-accounts/",
            params={"offset": offset, "limit": limit},
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("data", [])
        return []

    async def get_all_email_accounts(self) -> list[dict[str, Any]]:
        """
        Fetch ALL email accounts, handling pagination automatically.
        Smartlead enforces limit=100 maximum per page.
        """
        all_accounts: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            batch = await self.get_email_accounts(offset=offset, limit=limit)
            if not batch:
                break
            all_accounts.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        logger.info("Total email accounts fetched: %d", len(all_accounts))
        return all_accounts

    async def get_email_account(
        self,
        email_account_id: int,
    ) -> dict[str, Any]:
        """
        Fetch a single email account by ID.
        Endpoint: GET /email-accounts/{email_account_id}/
        """
        logger.debug("Fetching email account %d", email_account_id)
        try:
            result = await self._get(f"/email-accounts/{email_account_id}/")
            if isinstance(result, dict):
                return result
            return {}
        except SmartleadNotFoundError:
            logger.warning("Email account %d not found", email_account_id)
            return {}

    async def verify_connection(self) -> dict[str, Any]:
        """
        Perform a lightweight authenticated request to verify the API key works.
        Returns safe summary info (no secrets).
        """
        logger.info("Verifying Smartlead API connection")
        campaigns = await self.get_campaigns()
        return {
            "status": "connected",
            "campaigns_found": len(campaigns),
            "api_base_url": self._base_url,
        }
