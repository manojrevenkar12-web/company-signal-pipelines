"""Feeds as they arrive in production: one JSON file per feed and delivery day in a landing folder (an SFTP drop or
an S3 prefix synced to disk). A provider that redelivers a missed day puts it under redelivery/.

    landing/<feed>/<day>.json
    landing/<feed>/redelivery/<day>.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LandingSource:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _read(self, path: Path) -> list[dict[str, Any]] | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else None

    def fetch(self, feed: str, day: int) -> list[dict[str, Any]] | None:
        return self._read(self.root / feed / f"{day:03d}.json")

    def backfill(self, feed: str, day: int, today: int) -> list[dict[str, Any]] | None:
        return self._read(self.root / feed / "redelivery" / f"{day:03d}.json")


class ReplayModel:
    """Model answers recorded earlier (for example by a batch job against the Anthropic API), keyed by URL. Lets a
    pipeline rerun without paying for the same sentence twice."""

    def __init__(self, path: str | Path, tier: str):
        self.name = f"replay-{tier}"
        self.tier = tier
        self.answers: dict[str, list[Any]] = json.loads(Path(path).read_text())[tier]

    def label(self, article: dict[str, Any]) -> tuple[str, float, int]:
        a = self.answers.get(article["url"])
        if a is None:
            return "none", 0.0, 0
        return str(a[0]), float(a[1]), int(a[2])
