"""Unit tests for configuration module."""

from __future__ import annotations

import pytest

from shopee_scraper.utils.config import (
    AuthSettings,
    CORSSettings,
    RateLimitSettings,
)


@pytest.fixture(autouse=True)
def clear_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear environment variables that could affect config tests."""
    # Clear rate limit vars
    monkeypatch.delenv("RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("RATE_LIMIT_STORAGE", raising=False)
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    # Clear auth vars
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.delenv("API_KEY_HEADER_NAME", raising=False)
    # Clear CORS vars
    monkeypatch.delenv("CORS_ENABLED", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)


class TestRateLimitSettings:
    """Tests for RateLimitSettings class."""

    def test_default_values(self) -> None:
        """Test default configuration values (without .env influence)."""
        settings = RateLimitSettings(_env_file=None)  # type: ignore[call-arg]

        assert settings.enabled is False
        assert settings.requests_per_minute == 60
        assert settings.requests_per_hour == 1000
        assert settings.burst_limit == 10
        assert settings.storage == "memory"

    def test_redis_url_default(self) -> None:
        """Test default Redis URL (without .env influence)."""
        settings = RateLimitSettings(_env_file=None)  # type: ignore[call-arg]
        assert settings.redis_url == "redis://localhost:6379"


class TestCORSSettings:
    """Tests for CORSSettings class."""

    def test_default_values(self) -> None:
        """Test default CORS values."""
        settings = CORSSettings()

        assert settings.enabled is True
        assert settings.allow_origins == "*"
        assert settings.allow_credentials is False
        assert settings.max_age == 600

    def test_get_origins_list_wildcard(self) -> None:
        """Test origins list with wildcard."""
        settings = CORSSettings(allow_origins="*")
        assert settings.get_origins_list() == ["*"]

    def test_get_origins_list_multiple(self) -> None:
        """Test origins list with multiple origins."""
        settings = CORSSettings(
            allow_origins="https://example.com, https://api.example.com"
        )
        origins = settings.get_origins_list()
        assert len(origins) == 2
        assert "https://example.com" in origins
        assert "https://api.example.com" in origins

    def test_get_methods_list(self) -> None:
        """Test methods list parsing."""
        settings = CORSSettings(allow_methods="GET, POST, PUT")
        methods = settings.get_methods_list()
        assert methods == ["GET", "POST", "PUT"]

    def test_get_headers_list(self) -> None:
        """Test headers list parsing."""
        settings = CORSSettings(allow_headers="Content-Type, Authorization")
        headers = settings.get_headers_list()
        assert headers == ["Content-Type", "Authorization"]


class TestAuthSettings:
    """Tests for AuthSettings class."""

    def test_default_values(self) -> None:
        """Test default auth values (without .env influence)."""
        settings = AuthSettings(_env_file=None)  # type: ignore[call-arg]

        assert settings.auth_enabled is False
        assert settings.keys == ""
        assert settings.key_header_name == "X-API-Key"

    def test_get_keys_list_empty(self) -> None:
        """Test empty keys list."""
        settings = AuthSettings(keys="")
        assert settings.get_keys_list() == []

    def test_get_keys_list_single(self) -> None:
        """Test single key."""
        settings = AuthSettings(keys="sk_test123")
        assert settings.get_keys_list() == ["sk_test123"]

    def test_get_keys_list_multiple(self) -> None:
        """Test multiple keys."""
        settings = AuthSettings(keys="sk_key1, sk_key2, sk_key3")
        keys = settings.get_keys_list()
        assert len(keys) == 3
        assert "sk_key1" in keys
        assert "sk_key2" in keys
        assert "sk_key3" in keys

    def test_get_keys_list_whitespace_handling(self) -> None:
        """Test that whitespace is properly handled."""
        settings = AuthSettings(keys="  sk_key1  ,  sk_key2  ")
        keys = settings.get_keys_list()
        assert keys == ["sk_key1", "sk_key2"]
