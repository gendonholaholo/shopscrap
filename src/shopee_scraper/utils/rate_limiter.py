"""Rate limiting utilities."""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque


class RateLimiter:
    """Token bucket rate limiter with human-like delays."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_limit: int = 10,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._timestamps: deque[float] = deque(maxlen=requests_per_minute)

    async def acquire(self) -> None:
        """Wait until request is allowed."""
        now = time.monotonic()
        # Remove old timestamps
        while self._timestamps and now - self._timestamps[0] > 60:
            self._timestamps.popleft()
        # Check rate limit
        if len(self._timestamps) >= self.requests_per_minute:
            sleep_time = 60 - (now - self._timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        # Add human-like random delay
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)
        self._timestamps.append(time.monotonic())

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *args: object) -> None:
        pass
