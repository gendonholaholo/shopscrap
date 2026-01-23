"""Health checking utilities for monitoring system and application components."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class ComponentHealth:
    """Health status of an individual component."""

    name: str
    status: Literal["healthy", "degraded", "unhealthy"]
    message: str | None = None
    latency_ms: float | None = None


@dataclass
class HealthCheckResult:
    """Overall health check result."""

    status: Literal["healthy", "degraded", "unhealthy"]
    components: list[ComponentHealth]
    total_checks: int
    healthy_checks: int
    degraded_checks: int
    unhealthy_checks: int
    timestamp: datetime


class HealthChecker:
    """
    Comprehensive health checker for Shopee Scraper.

    Checks:
    - Disk space availability
    - Directory permissions
    - Browser availability
    - Session file validity
    """

    def __init__(
        self,
        data_dir: str = "./data",
        min_disk_space_mb: int = 500,
    ) -> None:
        """
        Initialize health checker.

        Args:
            data_dir: Data directory to check
            min_disk_space_mb: Minimum required disk space in MB
        """
        self.data_dir = Path(data_dir)
        self.min_disk_space_mb = min_disk_space_mb

    async def check_health(self) -> HealthCheckResult:
        """
        Run all health checks.

        Returns:
            HealthCheckResult with overall status and component details
        """
        components: list[ComponentHealth] = []

        # Run all checks
        components.append(await self._check_disk_space())
        components.append(await self._check_storage_directories())
        components.append(await self._check_browser_availability())

        # Calculate overall status
        total = len(components)
        healthy = sum(1 for c in components if c.status == "healthy")
        degraded = sum(1 for c in components if c.status == "degraded")
        unhealthy = sum(1 for c in components if c.status == "unhealthy")

        # Determine overall status
        overall_status: Literal["healthy", "degraded", "unhealthy"]
        if unhealthy > 0:
            overall_status = "unhealthy"
        elif degraded > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return HealthCheckResult(
            status=overall_status,
            components=components,
            total_checks=total,
            healthy_checks=healthy,
            degraded_checks=degraded,
            unhealthy_checks=unhealthy,
            timestamp=datetime.utcnow(),
        )

    async def _check_disk_space(self) -> ComponentHealth:
        """Check available disk space."""
        try:
            # Get disk usage stats
            usage = shutil.disk_usage(self.data_dir)
            free_mb = usage.free / (1024 * 1024)

            if free_mb >= self.min_disk_space_mb:
                return ComponentHealth(
                    name="disk_space",
                    status="healthy",
                    message=f"{free_mb:.0f}MB available",
                )
            elif free_mb >= self.min_disk_space_mb * 0.5:
                return ComponentHealth(
                    name="disk_space",
                    status="degraded",
                    message=f"Low disk space: {free_mb:.0f}MB available",
                )
            else:
                return ComponentHealth(
                    name="disk_space",
                    status="unhealthy",
                    message=f"Critical: Only {free_mb:.0f}MB available",
                )

        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return ComponentHealth(
                name="disk_space",
                status="unhealthy",
                message=f"Check failed: {e}",
            )

    async def _check_storage_directories(self) -> ComponentHealth:
        """Check storage directories are writable."""
        try:
            required_dirs = [
                self.data_dir / "output",
                self.data_dir / "sessions",
            ]

            issues = []
            for dir_path in required_dirs:
                # Create if not exists
                if not dir_path.exists():
                    try:
                        dir_path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        issues.append(f"{dir_path.name}: cannot create ({e})")
                        continue

                # Check writable
                if not dir_path.is_dir():
                    issues.append(f"{dir_path.name}: not a directory")
                elif not self._is_writable(dir_path):
                    issues.append(f"{dir_path.name}: not writable")

            if not issues:
                return ComponentHealth(
                    name="storage_directories",
                    status="healthy",
                    message="All directories accessible",
                )
            else:
                return ComponentHealth(
                    name="storage_directories",
                    status="unhealthy",
                    message="; ".join(issues),
                )

        except Exception as e:
            logger.error(f"Storage check failed: {e}")
            return ComponentHealth(
                name="storage_directories",
                status="unhealthy",
                message=f"Check failed: {e}",
            )

    async def _check_browser_availability(self) -> ComponentHealth:
        """Check if browser (Camoufox) is available."""
        try:
            # Try to import camoufox
            import camoufox  # noqa: F401

            return ComponentHealth(
                name="browser",
                status="healthy",
                message="Camoufox available",
            )

        except ImportError as e:
            logger.error(f"Browser check failed: {e}")
            return ComponentHealth(
                name="browser",
                status="unhealthy",
                message="Camoufox not installed",
            )
        except Exception as e:
            logger.error(f"Browser check failed: {e}")
            return ComponentHealth(
                name="browser",
                status="degraded",
                message=f"Check failed: {e}",
            )

    def _is_writable(self, path: Path) -> bool:
        """Check if directory is writable."""
        try:
            test_file = path / ".health_check_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False


# =============================================================================
# Convenience Functions
# =============================================================================


async def check_health(
    data_dir: str = "./data",
    min_disk_space_mb: int = 500,
) -> HealthCheckResult:
    """
    Quick health check function.

    Args:
        data_dir: Data directory to check
        min_disk_space_mb: Minimum required disk space

    Returns:
        HealthCheckResult
    """
    checker = HealthChecker(
        data_dir=data_dir,
        min_disk_space_mb=min_disk_space_mb,
    )
    return await checker.check_health()
