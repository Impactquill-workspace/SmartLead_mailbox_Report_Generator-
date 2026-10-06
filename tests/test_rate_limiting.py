"""
Tests for rate limiting, pacing, and 429 cooldown barrier in SmartleadApiClient.
"""
from __future__ import annotations

import asyncio
import time
import httpx
import pytest
import respx

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadRateLimitError
from app.core.config import Settings


BASE_URL = "https://server.smartlead.ai/api/v1"


def make_test_settings(interval: float = 0.05, max_retry_delay: float = 0.2) -> Settings:
    return Settings(
        smartlead_api_key="test-key-12345",
        database_url="postgresql+asyncpg://user:pass@localhost/test",
        smartlead_max_retries=2,
        smartlead_max_concurrency=3,
        smartlead_request_interval=interval,
        smartlead_max_retry_delay=max_retry_delay,
    )


@pytest.mark.asyncio
class TestRateLimiterPacing:

    @respx.mock
    async def test_requests_are_paced(self):
        """Sequential and concurrent requests must respect minimum request interval."""
        route = respx.get(f"{BASE_URL}/campaigns/").mock(
            return_value=httpx.Response(200, json=[])
        )
        interval = 0.05  # 50ms pacing
        settings = make_test_settings(interval=interval)

        start = time.perf_counter()
        async with SmartleadApiClient(settings) as client:
            # Dispatch 4 concurrent requests
            await asyncio.gather(*(client.get_campaigns() for _ in range(4)))
        elapsed = time.perf_counter() - start

        # 4 requests with 50ms pacing between each should take at least ~150ms
        assert elapsed >= (3 * interval * 0.8), f"Elapsed {elapsed}s was too fast for paced requests"
        assert route.call_count == 4


@pytest.mark.asyncio
class TestRateLimit429BarrierAndRetry:

    @respx.mock
    async def test_429_retries_and_succeeds(self):
        """When 429 is hit, the client must wait Retry-After and succeed on retry."""
        route = respx.get(f"{BASE_URL}/campaigns/")
        # First call fails with 429 Retry-After: 0.05
        # Second call succeeds with 200
        route.side_effect = [
            httpx.Response(429, json={"error": "Rate limit exceeded"}, headers={"Retry-After": "0.05"}),
            httpx.Response(200, json=[{"id": 1, "name": "Success"}]),
        ]

        settings = make_test_settings(interval=0.0, max_retry_delay=0.5)

        async with SmartleadApiClient(settings) as client:
            campaigns = await client.get_campaigns()

        assert len(campaigns) == 1
        assert campaigns[0]["name"] == "Success"
        assert route.call_count == 2

    @respx.mock
    async def test_global_barrier_pauses_other_workers(self):
        """When one request triggers 429, other workers pause until cooldown expires."""
        route = respx.get(f"{BASE_URL}/campaigns/")
        route.side_effect = [
            httpx.Response(429, json={"error": "Rate limited"}, headers={"Retry-After": "0.1"}),
            httpx.Response(200, json=[{"id": 1, "name": "Worker 1"}]),
            httpx.Response(200, json=[{"id": 2, "name": "Worker 2"}]),
        ]

        settings = make_test_settings(interval=0.0, max_retry_delay=0.5)

        async with SmartleadApiClient(settings) as client:
            results = await asyncio.gather(
                client.get_campaigns(),
                client.get_campaigns(),
            )

        assert len(results) == 2
        assert route.call_count == 3
