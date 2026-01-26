"""Proxy management and rotation utilities."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class ProxyConfig:
    """Single proxy configuration."""

    host: str
    port: int
    username: str = ""
    password: str = ""
    protocol: str = "http"  # http | socks5

    def to_playwright_proxy(self) -> dict[str, Any]:
        """Convert to Playwright proxy format."""
        proxy: dict[str, Any] = {
            "server": f"{self.protocol}://{self.host}:{self.port}",
        }
        if self.username and self.password:
            proxy["username"] = self.username
            proxy["password"] = self.password
        return proxy

    def to_url(self) -> str:
        """Convert to proxy URL string."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"


@dataclass
class ProxyPool:
    """Pool of proxies with rotation support."""

    proxies: list[ProxyConfig] = field(default_factory=list)
    _current_index: int = 0

    def add_proxy(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        protocol: str = "http",
    ) -> None:
        """Add a proxy to the pool."""
        proxy = ProxyConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            protocol=protocol,
        )
        self.proxies.append(proxy)
        logger.info(
            "Proxy added to pool", host=host, port=port, total=len(self.proxies)
        )

    def get_next(self) -> ProxyConfig | None:
        """Get next proxy in rotation (round-robin)."""
        if not self.proxies:
            return None
        proxy = self.proxies[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.proxies)
        return proxy

    def get_random(self) -> ProxyConfig | None:
        """Get a random proxy from the pool."""
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def remove_proxy(self, host: str, port: int) -> bool:
        """Remove a proxy from the pool (e.g., if blocked)."""
        for i, proxy in enumerate(self.proxies):
            if proxy.host == host and proxy.port == port:
                self.proxies.pop(i)
                logger.warning("Proxy removed from pool", host=host, port=port)
                return True
        return False

    @property
    def size(self) -> int:
        """Get number of proxies in pool."""
        return len(self.proxies)

    @property
    def is_empty(self) -> bool:
        """Check if pool is empty."""
        return len(self.proxies) == 0


# =============================================================================
# Proxy Configuration Loader
# =============================================================================


def load_proxies_from_env() -> ProxyPool:
    """Load proxy configuration from environment variables."""
    import os

    pool = ProxyPool()

    # Check if proxy is enabled
    proxy_enabled = os.getenv("PROXY_ENABLED", "false").lower() in ("true", "1", "yes")
    if not proxy_enabled:
        logger.info("Proxy disabled via PROXY_ENABLED=false")
        return pool

    # Single proxy from env
    proxy_host = os.getenv("PROXY_HOST", "")
    proxy_port = os.getenv("PROXY_PORT", "")

    if proxy_host and proxy_port:
        pool.add_proxy(
            host=proxy_host,
            port=int(proxy_port),
            username=os.getenv("PROXY_USERNAME", ""),
            password=os.getenv("PROXY_PASSWORD", ""),
            protocol=os.getenv("PROXY_PROTOCOL", "http"),
        )
        logger.info(f"Proxy loaded: {proxy_host}:{proxy_port}")

    return pool
