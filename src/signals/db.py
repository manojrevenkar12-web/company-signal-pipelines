"""Postgres: numbered plain-SQL migrations and writing a run's decisions into core."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg

from signals.config import ROOT, dsn
from signals.normalize import name_key

MIGRATIONS = ROOT / "migrations"


def connect(url: str | None = None) -> psycopg.Connection[Any]:
    return psycopg.connect(url or dsn(), autocommit=True)


def migrate(conn: psycopg.Connection[Any]) -> list[str]:
    conn.execute("create table if not exists public.schema_migration (name text primary key, "
                 "applied_at timestamptz not null default now())")
    done = {r[0] for r in conn.execute("select name from public.schema_migration").fetchall()}
    applied = []
    for path in sorted(Path(MIGRATIONS).glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text())  # type: ignore[arg-type]
            conn.execute("insert into public.schema_migration (name) values (%s)", (path.name,))
        applied.append(path.name)
    return applied


def reset(conn: psycopg.Connection[Any]) -> None:
    conn.execute("drop schema if exists raw cascade; drop schema if exists core cascade; "
                 "drop schema if exists ops cascade; drop schema if exists analytics cascade; "
                 "drop table if exists public.schema_migration")


def write_result(conn: psycopg.Connection[Any], result: Any, design_name: str) -> None:
    """Replace core with this run's decisions. Raw is untouched."""
    r = result
    with conn.transaction():
        conn.execute("truncate core.event_evidence, core.event, core.field_value, core.entity_name, "
                     "core.source_record, core.review_pair, core.article, core.entity cascade")
        with conn.cursor() as cur:
            by_id = {x.id: x for x in r.records}
            cur.executemany(
                "insert into core.entity (entity_id, is_customer, members) values (%s,%s,%s)",
                [(e, any(by_id[m].feed == "crm" for m in ms), len(ms)) for e, ms in r.resolution.members.items()])
            cur.executemany(
                "insert into core.source_record values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(x.id, x.feed, x.names, x.domain or None, x.city or None, x.country or None, x.founded,
                  x.identifier or None, r.resolution.entity_of[x.id]) for x in r.records])
            names = []
            for e, ms in r.resolution.members.items():
                golden = r.golden.get(e, {}).get("name")
                seen: set[str] = set()
                for n in ([str(golden.value)] if golden else []) + [n for m in ms for n in by_id[m].names]:
                    if n and n not in seen:
                        seen.add(n)
                        names.append((e, n, name_key(n), bool(golden and n == str(golden.value))))
            cur.executemany("insert into core.entity_name values (%s,%s,%s,%s)", names)
            cur.executemany(
                "insert into core.review_pair (record_a, record_b, score, reason) values (%s,%s,%s,%s) "
                "on conflict do nothing",
                [(p.a, p.b, round(p.score, 4), p.reason) for p in r.resolution_auto.review])
            news = {x.key: x.payload for x in r.lake.rows("news_mentions")}
            rows = []
            for url, d in r.decisions.items():
                lk, p = r.links[url], news.get(url, {})
                rows.append((url, p.get("published_on"), p.get("language"), p.get("title"), lk.corporate,
                             lk.startup, lk.status, lk.candidates, d.label, d.decided_by, round(d.confidence, 4),
                             round(d.cost_eur, 6), d.steps))
            cur.executemany("insert into core.article values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
            ev_rows, evid_rows = [], []
            for ev in r.events:
                eid = hashlib.sha1(f"{ev.entity}|{ev.kind}|{ev.on}".encode(), usedforsecurity=False).hexdigest()[:16]
                ev_rows.append((eid, ev.entity, ev.kind, ev.on, ev.sources))
                evid_rows += [(eid, x.source, x.ref, x.stated, x.seen) for x in ev.evidence]
            cur.executemany("insert into core.event values (%s,%s,%s,%s,%s) on conflict do nothing", ev_rows)
            cur.executemany("insert into core.event_evidence values (%s,%s,%s,%s,%s)", evid_rows)
            cur.executemany(
                "insert into core.field_value values (%s,%s,%s,%s,%s,%s)",
                [(fv.entity, fv.field, None if fv.value is None else str(fv.value), fv.source, fv.observed, fv.why)
                 for fields in r.golden.values() for fv in fields.values()])
            cur.executemany(
                "insert into ops.alert (feed, kind, hour, day, detail) values (%s,%s,%s,%s,%s) "
                "on conflict do nothing",
                [(a.feed, a.kind, a.hour, a.day, a.detail) for a in r.ingest.alerts])
        conn.execute("insert into ops.pipeline_run (design, entities, articles, events, seconds) "
                     "values (%s,%s,%s,%s,%s)",
                     (design_name, len(r.resolution.members), len(r.decisions), len(r.events),
                      json.dumps(r.stage_seconds)))
