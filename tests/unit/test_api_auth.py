"""Unit tests for API authentication."""

from __future__ import annotations

from shopee_scraper.api.auth import APIKeyManager


class TestAPIKeyManager:
    """Tests for APIKeyManager class."""

    def test_generate_key_format(self) -> None:
        """Test that generated keys have correct format."""
        key = APIKeyManager.generate_key()
        assert key.startswith("sk_")
        assert len(key) == 51  # sk_ + 48 hex chars

    def test_generate_key_custom_prefix(self) -> None:
        """Test generating key with custom prefix."""
        key = APIKeyManager.generate_key(prefix="test")
        assert key.startswith("test_")

    def test_generate_key_unique(self) -> None:
        """Test that generated keys are unique."""
        keys = [APIKeyManager.generate_key() for _ in range(100)]
        assert len(set(keys)) == 100

    def test_add_and_validate_key(self) -> None:
        """Test adding and validating a key."""
        manager = APIKeyManager()
        manager._valid_keys.clear()  # Clear any loaded keys

        test_key = "test_key_123"
        manager.add_key(test_key)

        assert manager.validate_key(test_key) is True
        assert manager.validate_key("wrong_key") is False

    def test_remove_key(self) -> None:
        """Test removing a key."""
        manager = APIKeyManager()
        manager._valid_keys.clear()

        test_key = "test_key_456"
        manager.add_key(test_key)
        assert manager.validate_key(test_key) is True

        manager.remove_key(test_key)
        assert manager.validate_key(test_key) is False

    def test_validate_empty_key(self) -> None:
        """Test that empty keys are rejected."""
        manager = APIKeyManager()
        assert manager.validate_key("") is False
        assert manager.validate_key(None) is False  # type: ignore

    def test_key_count(self) -> None:
        """Test key count property."""
        manager = APIKeyManager()
        manager._valid_keys.clear()

        assert manager.key_count == 0

        manager.add_key("key1")
        manager.add_key("key2")
        assert manager.key_count == 2

    def test_timing_attack_resistance(self) -> None:
        """Test that validation uses constant-time comparison."""
        manager = APIKeyManager()
        manager._valid_keys.clear()

        valid_key = "a" * 50
        manager.add_key(valid_key)

        # These should all take similar time due to hmac.compare_digest
        # We can't easily test timing, but we can verify the logic works
        assert manager.validate_key(valid_key) is True
        assert manager.validate_key("b" * 50) is False
        assert manager.validate_key("a" * 49) is False
