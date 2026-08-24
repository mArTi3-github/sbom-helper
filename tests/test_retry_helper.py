from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from purl_resolver.resolver.retry import RetryableErrorPolicy, RetryConfig, RetryHelper


class TestRetryableErrorPolicy:

    def test_timeout_is_retryable(self) -> None:
        assert RetryableErrorPolicy.is_retryable(httpx.TimeoutException("timeout"))

    def test_429_is_retryable(self) -> None:
        response = httpx.Response(429)
        exc = httpx.HTTPStatusError(
            "rate limit", request=httpx.Request("GET", "/"), response=response
        )
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_500_is_retryable(self) -> None:
        response = httpx.Response(500)
        exc = httpx.HTTPStatusError("error", request=httpx.Request("GET", "/"), response=response)
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_503_is_retryable(self) -> None:
        response = httpx.Response(503)
        exc = httpx.HTTPStatusError(
            "unavailable", request=httpx.Request("GET", "/"), response=response
        )
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_404_is_not_retryable(self) -> None:
        response = httpx.Response(404)
        exc = httpx.HTTPStatusError(
            "not found", request=httpx.Request("GET", "/"), response=response
        )
        assert not RetryableErrorPolicy.is_retryable(exc)

    def test_400_is_not_retryable(self) -> None:
        response = httpx.Response(400)
        exc = httpx.HTTPStatusError(
            "bad request", request=httpx.Request("GET", "/"), response=response
        )
        assert not RetryableErrorPolicy.is_retryable(exc)

    def test_network_error_is_retryable(self) -> None:
        assert RetryableErrorPolicy.is_retryable(httpx.ConnectError("connection refused"))

    def test_unrelated_exception_is_not_retryable(self) -> None:
        assert not RetryableErrorPolicy.is_retryable(ValueError("whatever"))


class TestRetryHelper:

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        mock = AsyncMock()
        mock.side_effect = ["ok"]
        result = await helper.execute(lambda: mock())
        assert result == "ok"
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        response = httpx.Response(429)
        mock = AsyncMock()
        mock.side_effect = [
            httpx.HTTPStatusError(
                "rate limit", request=httpx.Request("GET", "/"), response=response
            ),
            httpx.HTTPStatusError(
                "rate limit", request=httpx.Request("GET", "/"), response=response
            ),
            "ok",
        ]
        result = await helper.execute(lambda: mock())
        assert result == "ok"
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=2, base_cooldown_seconds=0.01))
        response = httpx.Response(503)
        exc = httpx.HTTPStatusError(
            "unavailable", request=httpx.Request("GET", "/"), response=response
        )
        mock = AsyncMock()
        mock.side_effect = [exc, exc]
        with pytest.raises(httpx.HTTPStatusError):
            await helper.execute(lambda: mock())
        assert mock.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        response = httpx.Response(404)
        exc = httpx.HTTPStatusError(
            "not found", request=httpx.Request("GET", "/"), response=response
        )
        mock = AsyncMock()
        mock.side_effect = [exc]
        with pytest.raises(httpx.HTTPStatusError):
            await helper.execute(lambda: mock())
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_cooldown_respects_linear_backoff(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.1))
        response = httpx.Response(429)
        exc = httpx.HTTPStatusError(
            "rate limit", request=httpx.Request("GET", "/"), response=response
        )
        mock = AsyncMock()
        mock.side_effect = [exc, exc, "ok"]
        import time
        t0 = time.monotonic()
        await helper.execute(lambda: mock())
        elapsed = time.monotonic() - t0
        # attempt 1: fail, wait 0.1*1 = 0.1s
        # attempt 2: fail, wait 0.1*2 = 0.2s
        # attempt 3: success
        assert elapsed >= 0.3
