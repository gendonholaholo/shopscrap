"""Tests for health checker."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shopee_scraper.utils.health_checker import HealthChecker, check_health


class TestHealthChecker:
    """Test HealthChecker class."""

    @pytest.mark.asyncio
    async def test_health_checker_initialization(self) -> None:
        """Test health checker can be initialized."""
        checker = HealthChecker(data_dir="./data", min_disk_space_mb=100)
        assert checker.data_dir == Path("./data")
        assert checker.min_disk_space_mb == 100

    @pytest.mark.asyncio
    async def test_check_health_returns_result(self) -> None:
        """Test health check returns valid result."""
        checker = HealthChecker(data_dir="./data")
        result = await checker.check_health()

        # Should have status
        assert result.status in ["healthy", "degraded", "unhealthy"]

        # Should have components
        assert len(result.components) > 0

        # Should have counts
        assert result.total_checks == len(result.components)
        assert (
            result.healthy_checks + result.degraded_checks + result.unhealthy_checks
            == result.total_checks
        )

        # Should have timestamp
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_disk_space_check(self) -> None:
        """Test disk space check."""
        checker = HealthChecker(data_dir="./data", min_disk_space_mb=1)
        result = await checker._check_disk_space()

        assert result.name == "disk_space"
        assert result.status in ["healthy", "degraded", "unhealthy"]
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_storage_directories_check(self) -> None:
        """Test storage directories check."""
        checker = HealthChecker(data_dir="./data")
        result = await checker._check_storage_directories()

        assert result.name == "storage_directories"
        assert result.status in ["healthy", "unhealthy"]

    @pytest.mark.asyncio
    async def test_browser_availability_check(self) -> None:
        """Test browser availability check."""
        checker = HealthChecker(data_dir="./data")
        result = await checker._check_browser_availability()

        assert result.name == "browser"
        assert result.status in ["healthy", "degraded", "unhealthy"]

    @pytest.mark.asyncio
    async def test_disk_space_low_warning(self) -> None:
        """Test disk space check with very high threshold."""
        # Get actual free space
        usage = shutil.disk_usage("./data")
        free_mb = usage.free / (1024 * 1024)

        # Set threshold higher than available
        checker = HealthChecker(
            data_dir="./data",
            min_disk_space_mb=int(free_mb * 2),
        )
        result = await checker._check_disk_space()

        # Should be degraded or unhealthy
        assert result.status in ["degraded", "unhealthy"]

    @pytest.mark.asyncio
    async def test_convenience_function(self) -> None:
        """Test convenience check_health function."""
        result = await check_health(data_dir="./data", min_disk_space_mb=100)

        assert result.status in ["healthy", "degraded", "unhealthy"]
        assert len(result.components) > 0
