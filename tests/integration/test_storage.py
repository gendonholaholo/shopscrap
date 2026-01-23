"""Integration tests for storage backends."""

import tempfile
from pathlib import Path

import pytest

from shopee_scraper.storage.json_storage import JsonStorage


@pytest.mark.integration
class TestJsonStorage:
    """Test JSON storage backend."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, sample_search_results: list) -> None:
        """Test saving and loading JSON data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = JsonStorage(output_dir=tmpdir)
            path = await storage.save(sample_search_results, "test")
            assert Path(path).exists()
            loaded = await storage.load("test.json")
            assert len(loaded) == 3
