"""The production path on Postgres: migrations, idempotent raw loads, core writes, stored review answers, the API
and the Dagster assets. Skipped without a database."""

import json
from datetime import date
from pathlib import Path

import pytest

from evals.drops import write_drops
from signals import db
from signals.config import design
from signals.ingest.lake import MemoryLake, PostgresLake
from signals.ingest.landing import LandingSource, ReplayModel
from signals.pipeline import decide, run
from signals.reviews import StoredDecisions

DAYS = 21


@pytest.fixture(scope="module")
def landed(world, tmp_path_factory):
    path = tmp_path_factory.mktemp("landing")
    write_drops(world, path, DAYS - 1)
    return path


@pytest.fixture(scope="module")
def conn(pg_dsn, monkeypatch_module):
    monkeypatch_module.setenv("SIGNALS_DSN", pg_dsn)
    c = db.connect(pg_dsn)
    db.migrate(c)
    return c


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def models(landed):
    a = landed / "model_answers.json"
    return ReplayModel(a, "cheap"), ReplayModel(a, "expensive")


@pytest.fixture(scope="module")
def pg_result(conn, landed, world):
    customers = json.loads((landed / "crm.json").read_text())
    r = run(LandingSource(landed), customers, world.start, DAYS, design(), *models(landed), lake=PostgresLake(conn))
    db.write_result(conn, r, "platform")
    return r


def test_postgres_and_memory_agree(pg_result, landed, world):
    customers = json.loads((landed / "crm.json").read_text())
    mem = run(LandingSource(landed), customers, world.start, DAYS, design(), *models(landed), lake=MemoryLake())
    assert len(mem.resolution.members) == len(pg_result.resolution.members)
    assert len(mem.events) == len(pg_result.events)
    assert [(a.feed, a.kind, a.hour) for a in mem.ingest.alerts] == \
        [(a.feed, a.kind, a.hour) for a in pg_result.ingest.alerts]


def test_loading_the_same_day_again_adds_no_rows(conn, landed, pg_result):
    before = conn.execute("select count(*) from raw.record").fetchone()[0]
    rows = LandingSource(landed).fetch("news_mentions", 3)
    PostgresLake(conn).load("news_mentions", "url", 3, rows, "backfill", 999, idempotent=True)
    assert conn.execute("select count(*) from raw.record").fetchone()[0] == before


def test_no_personal_field_leaves_raw(conn, pg_result):
    hits = conn.execute("select count(*) from core.source_record where array_to_string(names, ' ') like '%@%'"
                        " or domain like '%@%'").fetchone()[0]
    assert hits == 0
    assert conn.execute("select raw.redact_personal(0)").fetchone()[0] > 0
    assert conn.execute("select count(*) from raw.record where payload ? 'founder_email'").fetchone()[0] == 0


def test_a_reviewers_answer_is_applied_on_the_next_run(conn, pg_result, landed, world):
    by_id = {x.id: x for x in pg_result.records}
    res = pg_result.resolution_auto

    def idents(record_id):
        return {by_id[m].identifier for m in res.members[res.entity_of[record_id]] if by_id[m].identifier}

    # a pair a person may join: the two companies do not hold two different register numbers
    pair = next(p for p in res.review if len(idents(p.a) | idents(p.b)) <= 1)
    conn.execute("insert into ops.review_decision (kind, subject, answer, decided_by) values "
                 "('pair', %s, 'same', 'test') on conflict do nothing", (f"{pair.a}|{pair.b}",))
    customers = json.loads((landed / "crm.json").read_text())
    again = decide(PostgresLake(conn), pg_result.ingest, customers, world.start, DAYS, design(), *models(landed),
                   reviewer=StoredDecisions(conn))
    assert again.resolution.entity_of[pair.a] == again.resolution.entity_of[pair.b]
    assert again.reviewed_pairs == 1


def test_api_review_queue_and_answers(conn, pg_result):
    from fastapi.testclient import TestClient

    from signals.service.api import app

    client = TestClient(app)
    assert client.get("/health").json() == {"ok": True}
    q = client.get("/review").json()
    assert q["pairs"]
    p = q["pairs"][-1]
    r = client.post("/review/pairs", json={"record_a": p["record_a"], "record_b": p["record_b"],
                                           "answer": "different"}, headers={"x-reviewer": "analyst"})
    assert r.status_code == 200
    assert client.post("/review/pairs", json={"record_a": "x", "record_b": "y", "answer": "same"},
                       headers={"x-reviewer": "analyst"}).status_code == 404
    assert client.post("/review/labels", json={"url": "u", "label": "merger"},
                       headers={"x-reviewer": "analyst"}).status_code == 422
    assert "signals_review_pairs" in client.get("/metrics").text


def test_dagster_ingests_one_day_at_a_time(pg_dsn, landed, monkeypatch_module, conn):
    import dagster as dg

    from signals import orchestration as orch

    conn.execute("drop table if exists ops.ingest_state")
    res = {"warehouse": orch.Warehouse(dsn=pg_dsn), "landing": orch.Landing(path=str(Path(landed)))}
    for day in ("2026-06-01", "2026-06-02", "2026-06-03"):
        out = dg.materialize([orch.raw_feeds], partition_key=day, resources=res)
        assert out.success
    state = conn.execute("select state from ops.ingest_state").fetchone()[0]
    assert state["next_day"] == 3
    assert date.fromisoformat("2026-06-03") == orch.START.replace(day=3)
