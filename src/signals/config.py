"""Product settings. Reads config/pipelines.toml and config/gates.toml only; never the world's files."""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


@lru_cache
def settings() -> dict[str, Any]:
    with open(ROOT / "config" / "pipelines.toml", "rb") as f:
        return tomllib.load(f)


@lru_cache
def gates() -> dict[str, Any]:
    with open(ROOT / "config" / "gates.toml", "rb") as f:
        return tomllib.load(f)["gates"]


def design(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """The platform switches from [platform], with a design's overrides on top."""
    d = dict(settings()["platform"])
    d.update(overrides or {})
    return d


def dsn() -> str:
    return os.environ.get("SIGNALS_DSN", "postgresql://postgres@localhost:5433/signals")
