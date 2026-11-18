"""Intervals for every rate in the reports."""

from __future__ import annotations

import math


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float, float]:
    """(rate, low, high) for k successes in n trials."""
    if n <= 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def mean_ci(xs: list[float], z: float = 1.96) -> tuple[float, float, float]:
    if not xs:
        return (float("nan"), float("nan"), float("nan"))
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return (m, m, m)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    h = z * sd / math.sqrt(len(xs))
    return (m, m - h, m + h)


def rate(k: float, n: float) -> dict[str, float]:
    """A rate with its counts, so seeds can be pooled."""
    r, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": r, "low": lo, "high": hi}


def pool(rates: list[dict[str, float]]) -> dict[str, float]:
    return rate(sum(x["k"] for x in rates), sum(x["n"] for x in rates))
