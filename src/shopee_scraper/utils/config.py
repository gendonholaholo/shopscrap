"""Configuration management using Pydantic."""

from __future__ import annotations

import warnings
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserSettings(BaseSettings):
    """Browser configuration."""

    headless: bool = True
    timeout: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080


class ProxySettings(BaseSettings):
    """Proxy configuration for residential proxies."""

    model_config = SettingsConfigDict(
        env_prefix="PROXY_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable proxy")
    host: str = Field(default="", description="Proxy host (e.g., gate.smartproxy.com)")
    port: int = Field(default=0, description="Proxy port (e.g., 7000)")
    username: str = Field(default="", description="Proxy username")
    password: str = Field(default="", description="Proxy password")
    # Rotating proxy support
    rotate: bool = Field(default=True, description="Enable IP rotation per request")
    country: str = Field(default="id", description="Target country code (id=Indonesia)")

    def to_dict(self) -> dict | None:
        """Convert to dict for browser manager."""
        if not self.enabled or not self.host:
            return None
        return {
            "server": f"http://{self.host}:{self.port}",
            "username": self.username,
            "password": self.password,
        }

    def to_url(self) -> str | None:
        """Convert to proxy URL string."""
        if not self.enabled or not self.host:
            return None
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"http://{self.host}:{self.port}"


class RateLimitSettings(BaseSettings):
    """Rate limit configuration for API."""

    model_config = SettingsConfigDict(
        env_prefix="RATE_LIMIT_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable/disable rate limiting")
    requests_per_minute: int = Field(default=60, description="Max requests per minute")
    requests_per_hour: int = Field(default=1000, description="Max requests per hour")
    burst_limit: int = Field(default=10, description="Burst limit for short spikes")
    storage: str = Field(
        default="memory",
        description="Storage backend: memory or redis",
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis URL if using redis storage",
    )


class CORSSettings(BaseSettings):
    """CORS configuration for API."""

    model_config = SettingsConfigDict(
        env_prefix="CORS_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="Enable/disable CORS")
    allow_origins: str = Field(
        default="*",
        description="Comma-separated allowed origins (use * for all)",
    )
    allow_methods: str = Field(
        default="GET,POST,PUT,DELETE,OPTIONS",
        description="Comma-separated allowed HTTP methods",
    )
    allow_headers: str = Field(
        default="*",
        description="Comma-separated allowed headers (use * for all)",
    )
    allow_credentials: bool = Field(
        default=False,
        description="Allow credentials (cookies, auth headers)",
    )
    max_age: int = Field(
        default=600,
        description="Max age for preflight cache (seconds)",
    )

    def get_origins_list(self) -> list[str]:
        """Convert comma-separated origins to list."""
        if self.allow_origins == "*":
            return ["*"]
        return [o.strip() for o in self.allow_origins.split(",") if o.strip()]

    def get_methods_list(self) -> list[str]:
        """Convert comma-separated methods to list."""
        if self.allow_methods == "*":
            return ["*"]
        return [m.strip() for m in self.allow_methods.split(",") if m.strip()]

    def get_headers_list(self) -> list[str]:
        """Convert comma-separated headers to list."""
        if self.allow_headers == "*":
            return ["*"]
        return [h.strip() for h in self.allow_headers.split(",") if h.strip()]

    def is_permissive(self) -> bool:
        """Check if CORS is overly permissive (allows all origins)."""
        return self.allow_origins == "*"


class AuthSettings(BaseSettings):
    """API Authentication configuration."""

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        extra="ignore",
    )

    auth_enabled: bool = Field(
        default=False,
        description="Enable/disable API key authentication",
    )
    keys: str = Field(
        default="",
        description="Comma-separated list of valid API keys",
    )
    key_header_name: str = Field(
        default="X-API-Key",
        description="Header name for API key",
    )

    def get_keys_list(self) -> list[str]:
        """Convert comma-separated keys to list."""
        if not self.keys:
            return []
        return [k.strip() for k in self.keys.split(",") if k.strip()]


class JobQueueSettings(BaseSettings):
    """Job queue configuration (Redis-backed)."""

    model_config = SettingsConfigDict(
        env_prefix="JOB_QUEUE_",
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://localhost:6379/1",
        description="Redis URL for job queue (DB 1, separate from rate limiter)",
    )
    redis_pool_size: int = Field(
        default=10,
        description="Maximum connections in Redis pool",
    )
    redis_pool_timeout: int = Field(
        default=20,
        description="Timeout for getting connection from pool (seconds)",
    )
    max_concurrent: int = Field(
        default=3,
        description="Maximum concurrent job workers",
    )
    job_ttl_hours: int = Field(
        default=24,
        description="TTL for completed/failed jobs in hours",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for failed jobs",
    )
    retry_delay_seconds: int = Field(
        default=5,
        description="Base delay between retries (exponential backoff)",
    )
    handler_timeout_seconds: int = Field(
        default=3600,
        description="Maximum execution time per job handler (1 hour)",
    )
    max_queue_size: int = Field(
        default=100,
        description="Maximum pending jobs in queue (rejects when full)",
    )
    cleanup_interval_seconds: int = Field(
        default=3600,
        description="Interval between cleanup cycles",
    )


class CacheSettings(BaseSettings):
    """Cache configuration for scraped data."""

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(
        default=True,
        description="Enable/disable product caching",
    )
    product_ttl_seconds: int = Field(
        default=3600,
        description="TTL for cached products (default: 1 hour)",
    )
    review_ttl_seconds: int = Field(
        default=1800,
        description="TTL for cached reviews (default: 30 minutes)",
    )


class CaptchaSettings(BaseSettings):
    """CAPTCHA solver configuration (2Captcha/Anti-Captcha)."""

    model_config = SettingsConfigDict(
        env_prefix="CAPTCHA_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable CAPTCHA auto-solver")
    api_key: str = Field(default="", description="2Captcha or Anti-Captcha API key")
    provider: str = Field(
        default="2captcha",
        description="CAPTCHA provider: 2captcha or anticaptcha",
    )
    timeout: int = Field(default=120, description="Max wait time for solving (seconds)")
    max_retries: int = Field(default=3, description="Retry attempts for solving")


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration for scrape logging."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable PostgreSQL scrape logging")
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="shopee", description="Database user")
    password: str = Field(default="shopee_secret", description="Database password")
    name: str = Field(default="shopee-scraper-development", description="Database name")

    @property
    def url(self) -> str:
        """Build async PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class ExtensionSettings(BaseSettings):
    """Chrome Extension backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="EXTENSION_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="Enable Chrome Extension support")
    task_timeout_seconds: int = Field(
        default=300, description="Max time to wait for extension task result"
    )
    max_retries: int = Field(
        default=2, description="Max retry attempts for failed extension tasks"
    )
    heartbeat_interval_seconds: int = Field(
        default=30, description="Expected heartbeat interval from extension"
    )
    heartbeat_timeout_seconds: int = Field(
        default=90,
        description="Mark extension dead after this many seconds without heartbeat",
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="SHOPEE_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    env: str = "development"
    debug: bool = Field(default=False, description="Debug mode")
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    job_queue: JobQueueSettings = Field(default_factory=JobQueueSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    captcha: CaptchaSettings = Field(default_factory=CaptchaSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    extension: ExtensionSettings = Field(default_factory=ExtensionSettings)
    output_dir: Path = Path("./data/output")
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        """Validate security settings for production environment."""
        if self.env == "production":
            security_warnings: list[str] = []

            # Check authentication
            if not self.auth.auth_enabled:
                security_warnings.append(
                    "API_AUTH_ENABLED=false: Authentication is DISABLED in production! "
                    "Set API_AUTH_ENABLED=true and configure API_KEYS."
                )

            # Check rate limiting
            if not self.rate_limit.enabled:
                security_warnings.append(
                    "RATE_LIMIT_ENABLED=false: Rate limiting is DISABLED in production! "
                    "Set RATE_LIMIT_ENABLED=true to prevent DoS attacks."
                )

            # Check CORS
            if self.cors.is_permissive():
                security_warnings.append(
                    "CORS_ALLOW_ORIGINS=*: CORS allows ALL origins in production! "
                    "Set specific origins like CORS_ALLOW_ORIGINS=https://yourdomain.com"
                )

            # Check debug mode
            if self.debug:
                security_warnings.append(
                    "SHOPEE_DEBUG=true: Debug mode is ENABLED in production! "
                    "Set SHOPEE_DEBUG=false to hide error details."
                )

            # Emit warnings
            for warning_msg in security_warnings:
                warnings.warn(warning_msg, UserWarning, stacklevel=2)

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env == "production"

    def get_security_warnings(self) -> list[str]:
        """Get list of security warnings for current configuration."""
        warnings_list: list[str] = []

        if self.is_production:
            if not self.auth.auth_enabled:
                warnings_list.append("Authentication disabled in production")
            if not self.rate_limit.enabled:
                warnings_list.append("Rate limiting disabled in production")
            if self.cors.is_permissive():
                warnings_list.append("CORS allows all origins in production")
            if self.debug:
                warnings_list.append("Debug mode enabled in production")

        return warnings_list

    # Convenience properties for backward compatibility
    @property
    def api_auth_enabled(self) -> bool:
        """Check if API authentication is enabled."""
        return self.auth.auth_enabled

    @property
    def api_keys(self) -> str:
        """Get API keys string."""
        return self.auth.keys


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get cached settings instance (singleton)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def load_settings() -> Settings:
    """Load settings from environment (alias for get_settings)."""
    return get_settings()
