"""JSON file storage backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiofiles

from shopee_scraper.storage.base import BaseStorage


class JsonStorage(BaseStorage):
    """Store data as JSON files."""

    def __init__(self, output_dir: str = "./data/output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, data: list[dict[str, Any]], filename: str) -> str:
        """Save data to JSON file."""
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        path = self.output_dir / filename
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        return str(path)

    async def load(self, filename: str) -> list[dict[str, Any]]:
        """Load data from JSON file."""
        path = self.output_dir / filename
        async with aiofiles.open(path) as f:
            content = await f.read()
        return json.loads(content)
