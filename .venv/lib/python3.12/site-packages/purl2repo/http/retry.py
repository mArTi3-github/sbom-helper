"""Retry timing helpers."""

from __future__ import annotations

import random


def backoff_seconds(attempt: int, base: float = 0.2, jitter: float = 0.1) -> float:
    jitter_value: float = float(random.uniform(0, jitter))
    delay: float = base * (2.0**attempt) + jitter_value
    return delay
