"""
Tests for the Smartlead API client (mocked — no real API key required).

Tests:
1. Successful campaign fetch
2. 401 auth failure → SmartleadAuthError (not retried)
3. 429 rate limit → SmartleadRateLimitError
4. 500 server error → SmartleadServerError
5. Network timeout → SmartleadNetworkError
6. Invalid JSON response → SmartleadValidationError
7. API key never appears in exception messages
8. URL sanitization (api_key parameter masked)
"""
from __future__ import annotations

import pytest
import respx
import httpx
from unittest.mock import patch

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import (
    SmartleadAuthError,
    SmartleadNetworkError,
    SmartleadRateLimitError,
    SmartleadServerError,
    SmartleadValidationError,
)
from app.core.config import Settings


def make_mock_settings() -> Settings:
    """Create a Settings instance with a fake API key for testing."""
    return Settings(
        smartlead_api_key="test-api-key-12345678",
        database_url="postgresql+asyncpg://user:pass@localhost/test",
        smartlead_max_retries=1,  # Fail fast in tests
        smartlead_max_concurrency=1,
        smartlead_max_retry_delay=0.01,
        smartlead_request_interval=0.0,
    )


BASE_URL = "https://server.smartlead.ai/api/v1"

MOCK_CAMPAIGNS = [
    {"id": 1, "name": "Campaign A", "status": "ACTIVE", "client_id": 100},
    {"id": 2, "name": "Campaign B", "status": "PAUSED", "client_id": 100},
]

MOCK_EMAIL_ACCOUNTS = [
    {"id": 10, "from_email": "sales@example.com", "from_name": "Sales"},
    {"id": 11, "from_email": "info@example.com", "from_name": "Info"},
]

MOCK_ANALYTICS = [
    {"date": "2026-09-21", "sent_count": 50, "bounce_count": 1},
    {"date": "2026-09-22", "sent_count": 100, "bounce_count": 2},
]


@pytest.mark.asyncio
class TestSmartleadApiClient:

    @respx.mock
    async def test_get_campaigns_success(self):
        """Successful campaign fetch returns list of campaigns."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(200, json=MOCK_CAMPAIGNS)
        )
        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            campaigns = await client.get_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["name"] == "Campaign A"

    @respx.mock
    async def test_get_campaigns_with_client_id(self):
        """Campaigns filtered by client_id."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(200, json=[MOCK_CAMPAIGNS[0]])
        )
        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            campaigns = await client.get_campaigns(client_id=100)
        assert len(campaigns) == 1

    @respx.mock
    async def test_401_raises_auth_error(self):
        """HTTP 401 must raise SmartleadAuthError (not retried)."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadAuthError):
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()

    @respx.mock
    async def test_403_raises_auth_error(self):
        """HTTP 403 must raise SmartleadAuthError."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(403, json={"error": "Forbidden"})
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadAuthError):
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()

    @respx.mock
    async def test_429_raises_rate_limit_error(self):
        """HTTP 429 must raise SmartleadRateLimitError."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(429, json={"error": "Rate limited"})
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadRateLimitError):
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()

    @respx.mock
    async def test_429_with_retry_after_header(self):
        """Rate limit error captures Retry-After header value."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(
                429,
                json={"error": "Rate limited"},
                headers={"Retry-After": "30"},
            )
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadRateLimitError) as exc_info:
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()
        assert exc_info.value.retry_after == 30.0

    @respx.mock
    async def test_500_raises_server_error(self):
        """HTTP 500 must raise SmartleadServerError."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadServerError):
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()

    @respx.mock
    async def test_invalid_json_raises_validation_error(self):
        """Non-JSON response must raise SmartleadValidationError."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(200, text="not valid json")
        )
        settings = make_mock_settings()
        with pytest.raises(SmartleadValidationError):
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()

    @respx.mock
    async def test_get_campaign_email_accounts(self):
        """Email accounts endpoint returns correct data."""
        respx.get(f"{BASE_URL}/campaigns/1/email-accounts").mock(
            return_value=httpx.Response(200, json=MOCK_EMAIL_ACCOUNTS)
        )
        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            accounts = await client.get_campaign_email_accounts(1)
        assert len(accounts) == 2
        assert accounts[0]["from_email"] == "sales@example.com"

    @respx.mock
    async def test_get_analytics_by_date(self):
        """Analytics by date endpoint returns daily data."""
        respx.get(f"{BASE_URL}/campaigns/1/analytics-by-date").mock(
            return_value=httpx.Response(200, json=MOCK_ANALYTICS)
        )
        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            analytics = await client.get_campaign_analytics_by_date(
                1, "2026-09-21", "2026-09-27"
            )
        assert len(analytics) == 2

    @respx.mock
    async def test_get_campaign_statistics(self):
        """Campaign statistics endpoint returns total_stats and data."""
        respx.get(f"{BASE_URL}/campaigns/1/statistics").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total_stats": 150,
                    "data": [
                        {
                            "lead_email": "prospect@example.com",
                            "sent_time": "2026-09-25T10:00:00Z",
                            "is_bounced": False,
                        }
                    ],
                },
            )
        )
        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            stats = await client.get_campaign_statistics(
                campaign_id=1,
                start_date="2026-09-21",
                end_date="2026-09-27",
                limit=1,
            )
        assert stats["total_stats"] == 150
        assert len(stats["data"]) == 1

    @respx.mock
    async def test_analytics_service_get_campaign_totals(self):
        """AnalyticsService uses /statistics to get sent and bounced totals."""
        from datetime import date
        from app.services.analytics_service import AnalyticsService

        # Route 1: Bounced stats (registered first so it matches before the broader sent route)
        respx.get(
            f"{BASE_URL}/campaigns/1/statistics",
            params__contains={"email_status": "bounced"},
        ).mock(
            return_value=httpx.Response(200, json={"total_stats": 5, "data": []})
        )

        # Route 2: Sent stats
        respx.get(
            f"{BASE_URL}/campaigns/1/statistics",
        ).mock(
            return_value=httpx.Response(200, json={"total_stats": 250, "data": []})
        )

        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            service = AnalyticsService(client)
            sent, bounced = await service.get_campaign_totals(
                campaign_id=1,
                start_date=date(2026, 9, 21),
                end_date=date(2026, 9, 27),
            )

        assert sent == 250
        assert bounced == 5

    @respx.mock
    async def test_get_mailbox_health_metrics_success(self):
        """Official health metrics endpoint returns per-mailbox metrics."""
        mock_response = {
            "success": True,
            "data": {
                "email_health_metrics": [
                    {
                        "from_email": "abdulkittana@get-asecurecloud.com",
                        "sent": 168,
                        "bounced": 2,
                        "unique_lead_count": 151,
                        "bounce_rate": "1.32%",
                    }
                ]
            },
        }
        respx.get(f"{BASE_URL}/analytics/mailbox/name-wise-health-metrics").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        settings = make_mock_settings()
        async with SmartleadApiClient(settings) as client:
            metrics = await client.get_mailbox_health_metrics(
                start_date="2026-09-28",
                end_date="2026-10-04",
                client_ids="573725",
                full_data=True,
            )

        assert len(metrics) == 1
        assert metrics[0]["from_email"] == "abdulkittana@get-asecurecloud.com"
        assert metrics[0]["unique_lead_count"] == 151
        assert metrics[0]["sent"] == 168
        assert metrics[0]["bounced"] == 2
        assert metrics[0]["bounce_rate"] == "1.32%"

    async def test_api_key_not_in_repr(self):
        """API key must not appear in __repr__ or __str__."""
        settings = make_mock_settings()
        client = SmartleadApiClient(settings)
        assert "test-api-key-12345678" not in repr(client)
        assert "test-api-key-12345678" not in str(client)

    @respx.mock
    async def test_api_key_not_in_exception_message(self):
        """API key must not appear in any exception messages."""
        respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        settings = make_mock_settings()
        try:
            async with SmartleadApiClient(settings) as client:
                await client.get_campaigns()
        except SmartleadAuthError as exc:
            # The full API key must NOT appear in the error message
            assert "test-api-key-12345678" not in str(exc)


class TestUrlSanitization:
    """Tests for URL sanitization (api_key masking)."""

    def test_sanitize_url_masks_key(self):
        from app.core.security import sanitize_url_for_logging
        url = "https://server.smartlead.ai/api/v1/campaigns/?api_key=secretkey123"
        safe = sanitize_url_for_logging(url)
        assert "secretkey123" not in safe
        assert "****" in safe

    def test_sanitize_url_preserves_other_params(self):
        from app.core.security import sanitize_url_for_logging
        url = "https://server.smartlead.ai/api/v1/campaigns/?api_key=secretkey123&client_id=456"
        safe = sanitize_url_for_logging(url)
        assert "client_id=456" in safe
        assert "secretkey123" not in safe
