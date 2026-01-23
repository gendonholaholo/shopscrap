"""Configuration management using Pydantic."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserSettings(BaseSettings):
    """Browser configuration."""

    headless: bool = True
    timeout: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080


class ProxySettings(BaseSettings):
    """Proxy configuration."""

    enabled: bool = False
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""

    def to_dict(self) -> dict | None:
        if not self.enabled:
            return None
        return {
            "server": f"http://{self.host}:{self.port}",
            "username": self.username,
            "password": self.password,
        }


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


class CaptchaSettings(BaseSettings):
    """CAPTCHA solver configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, alias="USE_ANTICAPTCHA")
    api_key: str = Field(default="", alias="TWOCAPTCHA_API_KEY")
    timeout: int = 120  # Max wait time for solving (seconds)
    max_retries: int = 3  # Retry attempts for solving


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
    captcha: CaptchaSettings = Field(default_factory=CaptchaSettings)
    output_dir: Path = Path("./data/output")
    log_level: str = "INFO"

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
