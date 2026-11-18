"""Checks on every load and every hour. A monitor raises an alert; it never edits data."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class Alert:
    feed: str
    kind: str          # freshness | volume | schema | null_rate | duplicates | weekly_look
    hour: int
    detail: str
    day: int


def schema_problem(rows: list[dict[str, Any]], required: list[str]) -> str | None:
    if not rows:
        return None
    present = set().union(*(r.keys() for r in rows[:200]))
    missing = [c for c in required if c not in present]
    extra = sorted(present - set(required) - {"founder_email", "startup_domain"})
    if missing or extra:
        return f"missing {missing}, unexpected {extra}"
    return None


def volume_z(n: int, history: list[int]) -> float | None:
    if len(history) < 2:
        return None
    med = statistics.median(history)
    mad = statistics.median([abs(x - med) for x in history]) * 1.4826
    return (n - med) / max(mad, 1.0, 0.2 * med)


def null_rates(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, float]:
    if not rows:
        return {}
    return {f: sum(1 for r in rows if r.get(f) in (None, "", [])) / len(rows) for f in fields}


def duplicate_rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    keys = [str(r.get(key)) for r in rows]
    return 1 - len(set(keys)) / len(keys)
