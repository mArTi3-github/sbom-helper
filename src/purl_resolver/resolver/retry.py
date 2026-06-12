from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_cooldown_seconds: float = 5.0


class RetryableErrorPolicy:
    @staticmethod
    def is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (429, *range(500, 600))
        if isinstance(exc, httpx.HTTPError):
            return True
        return False


class RetryHelper:

    def __init__(self, config: RetryConfig) -> None:
        self._config = config

    async def execute[T](
        self,
        coroutine_factory: Callable[[], Awaitable[T]],
    ) -> T:
        max_attempts = self._config.max_attempts
        cooldown = self._config.base_cooldown_seconds
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await coroutine_factory()
            except Exception as exc:
                last_exc = exc
                if not RetryableErrorPolicy.is_retryable(exc):
                    raise
                if attempt < max_attempts:
                    wait = cooldown * attempt
                    logger.warning(
                        "Request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt, max_attempts, wait, exc,
                    )
                    await asyncio.sleep(wait)

        logger.warning(
            "Request failed after %d attempts: %s",
            max_attempts, last_exc,
        )
        raise last_exc