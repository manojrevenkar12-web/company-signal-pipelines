from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from world.generate import World, load  # noqa: E402


@pytest.fixture(scope="session")
def world() -> World:
    return World(load("world"))


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """A fresh database for the session; tests that need Postgres are skipped without one."""
    psycopg = pytest.importorskip("psycopg")
    admin = os.environ.get("SIGNALS_TEST_ADMIN_DSN", "postgresql://postgres@localhost:5433/postgres")
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            c.execute("drop database if exists signals_test with (force)")
            c.execute("create database signals_test")
    except psycopg.OperationalError:
        pytest.skip("no Postgres available")
    return admin.rsplit("/", 1)[0] + "/signals_test"
