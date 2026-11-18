"""The raw layer. A row is identified by (feed, source key, payload hash), so a redelivered row adds nothing.

Two implementations with the same behaviour: MemoryLake for fast runs and tests, PostgresLake for production
(INSERT ... ON CONFLICT DO NOTHING on the same key). Tests check they agree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


def payload_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:32]


@dataclass
class RawRow:
    feed: str
    key: str
    hash: str
    payload: dict[str, Any]
    delivery_day: int
    loaded_hour: int
    run_id: int


@dataclass
class LoadRun:
    id: int
    feed: str
    delivery_day: int
    kind: str            # scheduled | backfill
    hour: int
    rows: int
    new: int
    status: str          # loaded | quarantined
    note: str = ""


class Lake(Protocol):
    runs: list[LoadRun]

    def load(self, feed: str, key_field: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
             idempotent: bool) -> LoadRun: ...

    def quarantine(self, feed: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
                   note: str) -> LoadRun: ...

    def rows(self, feed: str) -> list[RawRow]: ...


@dataclass
class MemoryLake:
    runs: list[LoadRun] = field(default_factory=list)
    _rows: dict[str, list[RawRow]] = field(default_factory=dict)
    _seen: set[tuple[str, str, str]] = field(default_factory=set)

    def load(self, feed: str, key_field: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
             idempotent: bool) -> LoadRun:
        run = LoadRun(len(self.runs) + 1, feed, day, kind, hour, len(rows), 0, "loaded")
        bucket = self._rows.setdefault(feed, [])
        for r in rows:
            h = payload_hash(r)
            k = str(r.get(key_field))
            if idempotent and (feed, k, h) in self._seen:
                continue
            self._seen.add((feed, k, h))
            bucket.append(RawRow(feed, k, h, r, day, hour, run.id))
            run.new += 1
        self.runs.append(run)
        return run

    def quarantine(self, feed: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
                   note: str) -> LoadRun:
        run = LoadRun(len(self.runs) + 1, feed, day, kind, hour, len(rows), 0, "quarantined", note)
        self.runs.append(run)
        return run

    def rows(self, feed: str) -> list[RawRow]:
        return list(self._rows.get(feed, []))


class PostgresLake:
    """The same contract on Postgres: raw.load_run and raw.record with a unique (feed, source_key, payload_hash)."""

    def __init__(self, conn: Any):
        self.conn = conn
        self.runs: list[LoadRun] = []

    def _run(self, feed: str, day: int, kind: str, hour: int, rows: int, status: str, note: str) -> int:
        cur = self.conn.execute(
            "insert into raw.load_run (feed, delivery_day, kind, hour, rows, status, note) "
            "values (%s,%s,%s,%s,%s,%s,%s) returning id", (feed, day, kind, hour, rows, status, note))
        return int(cur.fetchone()[0])

    def load(self, feed: str, key_field: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
             idempotent: bool) -> LoadRun:
        rid = self._run(feed, day, kind, hour, len(rows), "loaded", "")
        with self.conn.cursor() as cur:
            cur.executemany(
                "insert into raw.record (feed, source_key, payload_hash, payload, delivery_day, loaded_hour, run_id)"
                " values (%s,%s,%s,%s,%s,%s,%s) on conflict (feed, source_key, payload_hash) do nothing",
                [(feed, str(r.get(key_field)), payload_hash(r) if idempotent else f"{payload_hash(r)}:{rid}:{i}",
                  json.dumps(r, default=str), day, hour, rid) for i, r in enumerate(rows)])
        new = int(self.conn.execute("select count(*) from raw.record where run_id = %s", (rid,)).fetchone()[0])
        self.conn.execute("update raw.load_run set new_rows = %s where id = %s", (new, rid))
        run = LoadRun(rid, feed, day, kind, hour, len(rows), new, "loaded")
        self.runs.append(run)
        return run

    def quarantine(self, feed: str, day: int, rows: list[dict[str, Any]], kind: str, hour: int,
                   note: str) -> LoadRun:
        rid = self._run(feed, day, kind, hour, len(rows), "quarantined", note)
        self.conn.execute("insert into raw.quarantine (run_id, feed, payload) values (%s,%s,%s)",
                          (rid, feed, json.dumps(rows[:50], default=str)))
        run = LoadRun(rid, feed, day, kind, hour, len(rows), 0, "quarantined", note)
        self.runs.append(run)
        return run

    def rows(self, feed: str) -> list[RawRow]:
        cur = self.conn.execute(
            "select feed, source_key, payload_hash, payload, delivery_day, loaded_hour, run_id from raw.record "
            "where feed = %s order by id", (feed,))
        return [RawRow(f, k, h, p, d, lh, rid) for f, k, h, p, d, lh, rid in cur.fetchall()]
