"""System resource monitoring utilities."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class SystemMetrics:
    """System resource metrics."""

    memory_available_mb: float | None = None
    memory_used_percent: float | None = None
    disk_free_mb: float | None = None
    disk_used_percent: float | None = None
    uptime_seconds: float = 0.0


class SystemMonitor:
    """
    Monitor system resources.

    Falls back gracefully if psutil is not available.
    """

    def __init__(self) -> None:
        """Initialize system monitor."""
        self._start_time = time.time()
        self._psutil_available = self._check_psutil()

    def _check_psutil(self) -> bool:
        """Check if psutil is available."""
        try:
            import psutil  # type: ignore[import-untyped]  # noqa: F401

            return True
        except ImportError:
            return False

    def get_metrics(self, data_dir: str = "./data") -> SystemMetrics:
        """
        Get system metrics.

        Args:
            data_dir: Directory to check disk usage for

        Returns:
            SystemMetrics with available information
        """
        metrics = SystemMetrics(
            uptime_seconds=time.time() - self._start_time,
        )

        if not self._psutil_available:
            return metrics

        try:
            import psutil

            # Memory metrics
            mem = psutil.virtual_memory()
            metrics.memory_available_mb = mem.available / (1024 * 1024)
            metrics.memory_used_percent = mem.percent

            # Disk metrics
            disk = psutil.disk_usage(data_dir)
            metrics.disk_free_mb = disk.free / (1024 * 1024)
            metrics.disk_used_percent = disk.percent

        except Exception:
            # If psutil fails, return partial metrics
            pass

        return metrics

    def get_uptime(self) -> float:
        """Get application uptime in seconds."""
        return time.time() - self._start_time


# Singleton instance
_monitor = SystemMonitor()


def get_system_metrics(data_dir: str = "./data") -> SystemMetrics:
    """
    Get current system metrics.

    Args:
        data_dir: Directory to check disk usage for

    Returns:
        SystemMetrics
    """
    return _monitor.get_metrics(data_dir)


def get_uptime() -> float:
    """
    Get application uptime in seconds.

    Returns:
        Uptime in seconds
    """
    return _monitor.get_uptime()
