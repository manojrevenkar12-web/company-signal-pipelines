"""Runs the feeds day by day: load, check, alert, and backfill what was missed once the feed is back.

The source is anything with fetch(feed, day) and backfill(feed, day, today); the product never knows what is behind
it (a landing folder in production, the simulation in evaluations). Hours count from the first day at 00:00.
The Ingestor keeps its state as plain data so an orchestrator can run one day at a time and store it between runs.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from signals.config import settings
from signals.ingest.lake import Lake
from signals.ingest.monitors import Alert, duplicate_rate, null_rates, schema_problem, volume_z


class Source(Protocol):
    def fetch(self, feed: str, day: int) -> list[dict[str, Any]] | None: ...

    def backfill(self, feed: str, day: int, today: int) -> list[dict[str, Any]] | None: ...


@dataclass
class FeedState:
    last_success_hour: int | None = None
    open_freshness: bool = False
    history: list[int] = field(default_factory=list)
    nulls: list[dict[str, float]] = field(default_factory=list)
    pending: list[int] = field(default_factory=list)       # delivery days to request again
    done: list[int] = field(default_factory=list)          # delivery days loaded cleanly


@dataclass
class IngestResult:
    alerts: list[Alert]
    backfilled_days: dict[str, list[int]]
    missing_days: dict[str, list[int]]


class Ingestor:
    def __init__(self, source: Source, lake: Lake, design: dict[str, Any], state: dict[str, Any] | None = None):
        self.source, self.lake, self.design = source, lake, design
        self.cfg = settings()
        self.feeds = self.cfg["feeds"]
        self.mon = self.cfg["monitors"]
        st = state or {}
        self.state = {f: FeedState(**st.get("feeds", {}).get(f, {})) for f in self.feeds}
        self.alerts: list[Alert] = [Alert(**a) for a in st.get("alerts", [])]
        self.backfilled: dict[str, list[int]] = st.get("backfilled", {f: [] for f in self.feeds})
        self.next_day: int = int(st.get("next_day", 0))

    def to_state(self) -> dict[str, Any]:
        return {"feeds": {f: asdict(s) for f, s in self.state.items()}, "alerts": [asdict(a) for a in self.alerts],
                "backfilled": self.backfilled, "next_day": self.next_day}

    def expected(self, feed: str, d: int) -> bool:
        return d % int(self.feeds[feed]["cadence_days"]) == 0

    def _accept(self, feed: str, d: int, rows: list[dict[str, Any]], kind: str, hour: int) -> bool:
        """Checks then loads. Returns True when the day is clean."""
        st, fc, mon, design = self.state[feed], self.feeds[feed], self.mon, self.design
        if design["monitors"]:
            problem = schema_problem(rows, fc["required"])
            if problem:
                self.lake.quarantine(feed, d, rows, kind, hour, problem)
                self.alerts.append(Alert(feed, "schema", hour, problem, d))
                if d not in st.pending:
                    st.pending.append(d)
                return False
        self.lake.load(feed, fc["key"], d, rows, kind, hour, design["idempotent_loads"])
        if not design["monitors"] or kind == "backfill" or d == 0:
            return True
        clean = True
        z = volume_z(len(rows), st.history[-int(mon["volume_window"]):]) \
            if len(st.history) >= int(mon["volume_min_history"]) else None
        if z is not None and z < -float(mon["volume_z"]):      # a spike is absorbed by idempotent keys
            self.alerts.append(Alert(feed, "volume", hour, f"{len(rows)} rows, robust z {z:.1f}", d))
            if d not in st.pending:
                st.pending.append(d)
            clean = False
        else:
            st.history.append(len(rows))
        rates = null_rates(rows, [c for c in fc["required"] if c != "funding_rounds"])
        if len(st.nulls) >= int(mon["volume_min_history"]):
            for fld, rate in rates.items():
                base = statistics.median(n.get(fld, 0.0) for n in st.nulls[-14:])
                if rate - base > float(mon["null_rate_jump"]):
                    self.alerts.append(Alert(feed, "null_rate", hour, f"{fld} null rate {rate:.0%} vs {base:.0%}", d))
                    if d not in st.pending:
                        st.pending.append(d)
                    clean = False
        if clean:
            st.nulls.append(rates)
        dup = duplicate_rate(rows, fc["key"])
        if dup > float(mon["duplicate_rate_max"]):
            self.alerts.append(Alert(feed, "duplicates", hour, f"{dup:.1%} repeated keys in one delivery", d))
        return clean

    def day(self, d: int) -> None:
        design, mon = self.design, self.mon
        hour0 = d * 24
        dh = int(mon["delivery_hour"])
        for feed in self.feeds:
            st = self.state[feed]
            if not self.expected(feed, d):
                continue
            rows = self.source.fetch(feed, d)
            hour = hour0 + dh
            if rows is None:
                if d not in st.pending:
                    st.pending.append(d)
                continue
            ok = self._accept(feed, d, rows, "scheduled", hour)
            st.last_success_hour = hour
            st.open_freshness = False
            if ok:
                st.done.append(d)
                if d in st.pending:
                    st.pending.remove(d)
            # the feed is back: ask for what it missed
            if design["backfill"] and ok:
                for missed in sorted(st.pending):
                    if missed >= d:
                        continue
                    again = self.source.backfill(feed, missed, d)
                    if again is None:
                        continue
                    if self._accept(feed, missed, again, "backfill", hour + 1):
                        st.pending.remove(missed)
                        st.done.append(missed)
                        self.backfilled.setdefault(feed, []).append(missed)
        for h in range(hour0, hour0 + 24):
            for feed in self.feeds:
                st = self.state[feed]
                if design["monitors"]:
                    if st.last_success_hour is not None and not st.open_freshness and \
                            h - st.last_success_hour > int(self.feeds[feed]["sla_hours"]):
                        st.open_freshness = True
                        self.alerts.append(Alert(feed, "freshness", h,
                                                 f"no load for {h - st.last_success_hour} h", d))
                elif d % 7 == 0 and d > 0 and h == hour0 + int(mon["weekly_look_hour"]):
                    unseen = [x for x in range(d - 7, d) if self.expected(feed, x) and x not in st.done]
                    if unseen:
                        self.alerts.append(Alert(feed, "weekly_look", h, f"no file on days {unseen}", d))
        if not design["monitors"]:
            for feed in self.feeds:
                st = self.state[feed]
                if self.expected(feed, d) and d not in st.pending and d not in st.done:
                    st.done.append(d)
        self.next_day = d + 1

    def result(self) -> IngestResult:
        missing = {f: sorted(x for x in range(self.next_day) if self.expected(f, x) and x not in self.state[f].done)
                   for f in self.feeds}
        return IngestResult(list(self.alerts), {f: list(v) for f, v in self.backfilled.items()}, missing)


def run_ingest(source: Source, lake: Lake, days: int, design: dict[str, Any]) -> IngestResult:
    ing = Ingestor(source, lake, design)
    for d in range(days):
        ing.day(d)
    return ing.result()
