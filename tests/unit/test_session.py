"""Unit tests for SessionManager."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from shopee_scraper.core.session import SessionManager


if TYPE_CHECKING:
    from pathlib import Path


class TestSessionManagerInit:
    """Tests for SessionManager initialization."""

    def test_init_creates_session_dir(self, tmp_path: Path) -> None:
        """Session directory is created on init if it doesn't exist."""
        session_dir = tmp_path / "sessions"
        assert not session_dir.exists()

        manager = SessionManager(session_dir=str(session_dir))

        assert session_dir.exists()
        assert manager.session_dir == session_dir

    def test_init_existing_dir_no_error(self, tmp_path: Path) -> None:
        """Existing session directory does not cause error."""
        session_dir = tmp_path / "sessions"
        session_dir.mkdir()

        manager = SessionManager(session_dir=str(session_dir))

        assert manager.session_dir == session_dir

    def test_init_default_not_logged_in(self, tmp_path: Path) -> None:
        """Manager starts with logged out state."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager.is_logged_in is False

    def test_init_captcha_solver_optional(self, tmp_path: Path) -> None:
        """Captcha solver is optional and defaults to None."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager.captcha_solver is None
        assert manager.use_anticaptcha is False


class TestCookieManagement:
    """Tests for cookie save/load functionality."""

    def test_save_cookies_creates_file(self, tmp_path: Path) -> None:
        """Saving cookies creates JSON file with proper structure."""
        manager = SessionManager(session_dir=str(tmp_path))
        cookies = [
            {"name": "SPC_EC", "value": "abc123", "domain": ".shopee.co.id"},
            {"name": "SPC_ST", "value": "xyz789", "domain": ".shopee.co.id"},
        ]

        path = manager.save_cookies(cookies, name="test")

        assert path.exists()
        assert path.name == "test_cookies.json"

        with path.open() as f:
            data = json.load(f)

        assert "cookies" in data
        assert "saved_at" in data
        assert "expires_at" in data
        assert len(data["cookies"]) == 2

    def test_save_cookies_default_name(self, tmp_path: Path) -> None:
        """Default session name is 'default'."""
        manager = SessionManager(session_dir=str(tmp_path))

        path = manager.save_cookies([], name="default")

        assert path.name == "default_cookies.json"

    def test_load_cookies_file_not_found(self, tmp_path: Path) -> None:
        """Loading non-existent cookies returns None."""
        manager = SessionManager(session_dir=str(tmp_path))

        result = manager.load_cookies(name="nonexistent")

        assert result is None

    def test_load_cookies_valid_json(self, tmp_path: Path) -> None:
        """Loading valid cookies file returns cookie list."""
        manager = SessionManager(session_dir=str(tmp_path))
        test_cookies = [{"name": "SPC_EC", "value": "test123"}]

        # Create valid cookie file
        cookie_file = tmp_path / "test_cookies.json"
        expires = (datetime.now() + timedelta(days=7)).isoformat()
        cookie_file.write_text(
            json.dumps(
                {
                    "cookies": test_cookies,
                    "saved_at": datetime.now().isoformat(),
                    "expires_at": expires,
                }
            )
        )

        result = manager.load_cookies(name="test")

        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "SPC_EC"

    def test_load_cookies_expired_returns_none(self, tmp_path: Path) -> None:
        """Expired cookies file returns None and is deleted."""
        manager = SessionManager(session_dir=str(tmp_path))

        # Create expired cookie file
        cookie_file = tmp_path / "expired_cookies.json"
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        cookie_file.write_text(
            json.dumps(
                {
                    "cookies": [{"name": "old"}],
                    "saved_at": datetime.now().isoformat(),
                    "expires_at": expired,
                }
            )
        )

        result = manager.load_cookies(name="expired")

        assert result is None
        assert not cookie_file.exists()  # File should be deleted

    def test_clear_session_deletes_file(self, tmp_path: Path) -> None:
        """Clearing session deletes the cookie file."""
        manager = SessionManager(session_dir=str(tmp_path))

        # Create a session file
        manager.save_cookies([{"name": "test"}], name="to_clear")
        cookie_file = tmp_path / "to_clear_cookies.json"
        assert cookie_file.exists()

        manager.clear_session(name="to_clear")

        assert not cookie_file.exists()

    def test_clear_session_nonexistent_no_error(self, tmp_path: Path) -> None:
        """Clearing non-existent session does not raise error."""
        manager = SessionManager(session_dir=str(tmp_path))

        # Should not raise
        manager.clear_session(name="nonexistent")


class TestUrlDetection:
    """Tests for URL pattern detection methods."""

    def test_is_logged_in_url_with_is_logged_in_param(self, tmp_path: Path) -> None:
        """URL with is_logged_in=true indicates logged in."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager._is_logged_in_url("https://shopee.co.id/?is_logged_in=true")
        assert manager._is_logged_in_url("https://shopee.co.id/home?is_logged_in=true")

    def test_is_logged_in_url_with_is_from_login_param(self, tmp_path: Path) -> None:
        """URL with is_from_login=true indicates logged in."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager._is_logged_in_url("https://shopee.co.id/?is_from_login=true")

    def test_is_logged_in_url_normal_url_false(self, tmp_path: Path) -> None:
        """Normal URLs without login params return False."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert not manager._is_logged_in_url("https://shopee.co.id/")
        assert not manager._is_logged_in_url("https://shopee.co.id/product/123/456")
        assert not manager._is_logged_in_url("https://shopee.co.id/buyer/login")

    def test_is_on_verification_page_login_page(self, tmp_path: Path) -> None:
        """Login page URL is detected as verification page."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager._is_on_verification_page("https://shopee.co.id/buyer/login")
        assert manager._is_on_verification_page(
            "https://shopee.co.id/buyer/login?next=/"
        )

    def test_is_on_verification_page_verify_page(self, tmp_path: Path) -> None:
        """Verify URLs are detected as verification pages."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager._is_on_verification_page("https://shopee.co.id/verify/captcha")
        assert manager._is_on_verification_page("https://shopee.co.id/verify/traffic")
        assert manager._is_on_verification_page("https://shopee.co.id/verify/otp")

    def test_is_on_verification_page_logged_in_url_false(self, tmp_path: Path) -> None:
        """Login page with logged_in param is NOT verification page."""
        manager = SessionManager(session_dir=str(tmp_path))

        # Even though it has /buyer/login, the is_logged_in param takes precedence
        assert not manager._is_on_verification_page(
            "https://shopee.co.id/buyer/login?is_logged_in=true"
        )

    def test_is_on_verification_page_normal_url_false(self, tmp_path: Path) -> None:
        """Normal URLs are not verification pages."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert not manager._is_on_verification_page("https://shopee.co.id/")
        assert not manager._is_on_verification_page(
            "https://shopee.co.id/product/123/456"
        )


class TestSessionState:
    """Tests for session state property."""

    def test_is_logged_in_property(self, tmp_path: Path) -> None:
        """is_logged_in property reflects internal state."""
        manager = SessionManager(session_dir=str(tmp_path))

        assert manager.is_logged_in is False

        manager._is_logged_in = True
        assert manager.is_logged_in is True


class TestRestoreSession:
    """Tests for session restoration."""

    @pytest.mark.asyncio
    async def test_restore_session_no_cookies(self, tmp_path: Path) -> None:
        """Restore returns False when no cookies exist."""
        manager = SessionManager(session_dir=str(tmp_path))
        mock_browser = MagicMock()

        result = await manager.restore_session(mock_browser, "nonexistent")

        assert result is False
        assert manager.is_logged_in is False

    @pytest.mark.asyncio
    async def test_restore_session_with_cookies(self, tmp_path: Path) -> None:
        """Restore returns True and sets cookies when file exists."""
        manager = SessionManager(session_dir=str(tmp_path))

        # Create valid cookie file
        test_cookies = [{"name": "SPC_EC", "value": "test"}]
        manager.save_cookies(test_cookies, name="valid")

        mock_browser = MagicMock()
        mock_browser.set_cookies = AsyncMock()

        result = await manager.restore_session(mock_browser, "valid")

        assert result is True
        assert manager.is_logged_in is True
        mock_browser.set_cookies.assert_called_once()
