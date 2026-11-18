"""Read API for the console and for analysts: feed health, company search, a company's golden record with
provenance, signals, and the review queues. Reviewers' answers are written to ops.review_decision and applied on the
next run. Reads the analytics marts dbt builds and the core tables; never the raw layer's personal fields."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from signals.config import dsn, settings
from signals.normalize import name_key

app = FastAPI(title="Company signal pipelines", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("SIGNALS_CORS", "http://localhost:5173").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@contextmanager
def conn() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(dsn(), row_factory=dict_row, autocommit=True) as c:  # type: ignore[arg-type]
        yield c


def rows(sql: str, *args: Any) -> list[dict[str, Any]]:
    with conn() as c:
        return list(c.execute(sql, args).fetchall())  # type: ignore[arg-type]


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        rows("select 1")
        return {"ok": True}
    except psycopg.Error as e:  # pragma: no cover - only without a database
        raise HTTPException(503, f"database unreachable: {e.__class__.__name__}") from e


@app.get("/feeds")
def feeds() -> dict[str, Any]:
    cfg = settings()["feeds"]
    health = {r["feed"]: r for r in rows("select * from analytics.feed_health")}
    alerts = rows("select feed, kind, hour, day, detail from ops.alert order by hour")
    runs = rows("select feed, delivery_day, kind, status, rows, new_rows from raw.load_run order by id")
    return {"feeds": [{"feed": f, "description": c["description"], "sla_hours": c["sla_hours"],
                       "cadence_days": c["cadence_days"], **{k: v for k, v in health.get(f, {}).items() if k != "feed"}}
                      for f, c in cfg.items()],
            "alerts": alerts, "runs": runs}


@app.get("/companies/search")
def search(q: str = Query(min_length=2, max_length=120), limit: int = Query(10, ge=1, le=50)) -> list[dict[str, Any]]:
    key = name_key(q)
    return rows(
        "select n.entity_id, c.name, c.city, c.country, c.status, max(similarity(n.name_key, %s)) as score "
        "from core.entity_name n join analytics.companies c using (entity_id) "
        "where n.name_key %% %s or n.name_key = %s "
        "group by n.entity_id, c.name, c.city, c.country, c.status order by score desc limit %s",
        key, key, key, limit)


@app.get("/companies/{entity_id}")
def company(entity_id: str) -> dict[str, Any]:
    found = rows("select * from analytics.companies where entity_id = %s", entity_id)
    if not found:
        raise HTTPException(404, "no such company")
    return {"company": found[0],
            "fields": rows("select field, value, source, observed, why from core.field_value where entity_id = %s "
                           "order by field", entity_id),
            "records": rows("select record_id, feed, names, domain, city, country, founded from core.source_record "
                            "where entity_id = %s order by feed", entity_id),
            "signals": rows("select kind, event_date, sources, first_seen from analytics.company_signals "
                            "where entity_id = %s order by event_date", entity_id),
            "relationships": rows(
                "select r.relationship, r.articles, r.first_seen, r.last_seen, c.name as corporate "
                "from analytics.relationships r join analytics.companies c on c.entity_id = r.corporate_entity "
                "where r.startup_entity = %s order by r.last_seen desc", entity_id)}


@app.get("/signals")
def signals(kind: str | None = None, limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
    if kind:
        return rows("select * from analytics.company_signals where kind = %s order by event_date desc limit %s",
                    kind, limit)
    return rows("select * from analytics.company_signals order by event_date desc limit %s", limit)


@app.get("/review")
def review(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    pairs = rows(
        "select p.record_a, p.record_b, p.score, p.reason, a.feed as feed_a, a.names as names_a, a.domain as domain_a,"
        " a.city as city_a, a.founded as founded_a, b.feed as feed_b, b.names as names_b, b.domain as domain_b, "
        " b.city as city_b, b.founded as founded_b "
        "from core.review_pair p join core.source_record a on a.record_id = p.record_a "
        "join core.source_record b on b.record_id = p.record_b "
        "where not exists (select 1 from ops.review_decision d where d.kind = 'pair' "
        "                  and d.subject = p.record_a || '|' || p.record_b) "
        "order by p.score desc limit %s", limit)
    open_articles = (
        "from core.article a where (a.decided_by = 'review' or (a.link_status = 'ambiguous' and a.label <> 'none' "
        "and cardinality(a.candidates) <= %s)) and not exists "
        "(select 1 from ops.review_decision d where d.subject = a.url)")
    most = int(settings()["linking"]["review_max_candidates"])
    articles = rows(
        "select a.url, a.title, a.label, a.confidence, a.steps, a.link_status, a.decided_by, "
        "  (select coalesce(json_agg(json_build_object("
        "     'entity_id', e,"
        "     'name', (select value from core.field_value f where f.entity_id = e and f.field = 'name'),"
        "     'city', (select value from core.field_value f where f.entity_id = e and f.field = 'city'),"
        "     'country', (select value from core.field_value f where f.entity_id = e and f.field = 'country'))),"
        "   '[]'::json) from unnest(a.candidates) as e) as candidates "
        + open_articles + " order by a.published_on desc limit %s", most, limit)
    totals = rows(
        "select (select count(*) from core.review_pair p where not exists (select 1 from ops.review_decision d "
        "        where d.kind = 'pair' and d.subject = p.record_a || '|' || p.record_b)) as pairs, "
        "       (select count(*) " + open_articles + ") as articles", most)[0]
    return {"pairs": pairs, "articles": articles, "totals": totals}


class PairAnswer(BaseModel):
    record_a: str
    record_b: str
    answer: str = Field(pattern="^(same|different)$")


class LabelAnswer(BaseModel):
    url: str
    label: str


class LinkAnswer(BaseModel):
    url: str
    entity_id: str


@app.post("/review/pairs")
def answer_pair(a: PairAnswer, x_reviewer: str = Header(min_length=2)) -> dict[str, str]:
    with conn() as c:
        if not c.execute("select 1 from core.review_pair where record_a = %s and record_b = %s",
                         (a.record_a, a.record_b)).fetchone():
            raise HTTPException(404, "no such pair in the queue")
        c.execute("insert into ops.review_decision (kind, subject, answer, decided_by) values ('pair', %s, %s, %s) "
                  "on conflict (kind, subject) do update set answer = excluded.answer, "
                  "decided_by = excluded.decided_by, decided_at = now()",
                  (f"{a.record_a}|{a.record_b}", a.answer, x_reviewer))
    return {"saved": "applied on the next run"}


@app.post("/review/labels")
def answer_label(a: LabelAnswer, x_reviewer: str = Header(min_length=2)) -> dict[str, str]:
    if a.label not in settings()["classification"]["labels"]:
        raise HTTPException(422, "unknown label")
    with conn() as c:
        c.execute("insert into ops.review_decision (kind, subject, answer, decided_by) values ('label', %s, %s, %s) "
                  "on conflict (kind, subject) do update set answer = excluded.answer, "
                  "decided_by = excluded.decided_by, decided_at = now()", (a.url, a.label, x_reviewer))
    return {"saved": "applied on the next run"}


@app.post("/review/links")
def answer_link(a: LinkAnswer, x_reviewer: str = Header(min_length=2)) -> dict[str, str]:
    with conn() as c:
        row = c.execute("select candidates from core.article where url = %s", (a.url,)).fetchone()
        if not row or a.entity_id not in row["candidates"]:  # type: ignore[index]
            raise HTTPException(422, "that company is not one of the article's candidates")
        c.execute("insert into ops.review_decision (kind, subject, answer, decided_by) values ('link', %s, %s, %s) "
                  "on conflict (kind, subject) do update set answer = excluded.answer, "
                  "decided_by = excluded.decided_by, decided_at = now()", (a.url, a.entity_id, x_reviewer))
    return {"saved": "applied on the next run"}


@app.get("/costs")
def costs() -> list[dict[str, Any]]:
    return rows("select * from analytics.classification_cost order by articles desc")


@app.get("/dictionary")
def dictionary() -> list[dict[str, Any]]:
    """Every column a consumer can read, with its type; descriptions come from the dbt docs."""
    return rows(
        "select c.table_name, c.column_name, c.data_type, "
        "       col_description(format('%%I.%%I', c.table_schema, c.table_name)::regclass, c.ordinal_position) "
        "       as description "
        "from information_schema.columns c where c.table_schema = 'analytics' "
        "order by c.table_name, c.ordinal_position")


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    q = rows("select (select count(*) from core.review_pair) as pairs, "
             "(select count(*) from ops.review_decision) as answered, "
             "(select count(*) from ops.alert) as alerts, "
             "(select count(*) from core.event) as events, "
             "(select coalesce(sum(cost_eur), 0) from core.article) as cost")[0]
    return (f"signals_review_pairs {q['pairs']}\nsignals_review_answered {q['answered']}\n"
            f"signals_alerts_total {q['alerts']}\nsignals_events {q['events']}\n"
            f"signals_classification_cost_eur {float(q['cost'])}\n")
