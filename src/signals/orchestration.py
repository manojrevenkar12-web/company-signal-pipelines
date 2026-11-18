"""Dagster definitions: daily-partitioned raw loads with checks, then the decisions, then the dbt marts.

    dagster dev -m signals.orchestration

raw_feeds runs one day at a time and keeps the Ingestor's state in ops.ingest_state, so monitors remember their
history between runs. A sensor reacts to a provider's redelivery file without waiting for the next morning.
"""


import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import dagster as dg

from signals import db
from signals.config import ROOT, design, settings
from signals.ingest.lake import PostgresLake
from signals.ingest.landing import LandingSource, ReplayModel
from signals.ingest.runner import Ingestor
from signals.pipeline import decide

ORCH = settings()["orchestration"]
START = date.fromisoformat(ORCH["start_date"])
daily = dg.DailyPartitionsDefinition(start_date=ORCH["start_date"], timezone=ORCH["timezone"])


class Warehouse(dg.ConfigurableResource):  # type: ignore[type-arg]
    dsn: str = ""

    def conn(self) -> Any:
        c = db.connect(self.dsn or None)
        db.migrate(c)
        c.execute("create table if not exists ops.ingest_state (id int primary key, state jsonb not null)")
        return c


class Landing(dg.ConfigurableResource):  # type: ignore[type-arg]
    path: str = str(ROOT / ORCH["landing"])


def _day(partition_key: str) -> int:
    return (date.fromisoformat(partition_key) - START).days


@dg.asset(partitions_def=daily, group_name="ingest",
          description="Load every feed's delivery for the day: contract, volume and null-rate checks, quarantine, "
                      "idempotent rows, and backfills of missed days once a feed is back.")
def raw_feeds(context: dg.AssetExecutionContext, warehouse: Warehouse, landing: Landing) -> dg.MaterializeResult:
    d = _day(context.partition_key)
    conn = warehouse.conn()
    row = conn.execute("select state from ops.ingest_state where id = 1").fetchone()
    ing = Ingestor(LandingSource(landing.path), PostgresLake(conn), design(), row[0] if row else None)
    if ing.next_day > d:
        context.log.info(f"day {d} already ingested (next day {ing.next_day})")
    for x in range(ing.next_day, d + 1):     # catch up in order: monitors need the days before
        ing.day(x)
    conn.execute("insert into ops.ingest_state values (1, %s) on conflict (id) do update set state = excluded.state",
                 (json.dumps(ing.to_state()),))
    for a in ing.alerts:
        conn.execute("insert into ops.alert (feed, kind, hour, day, detail) values (%s,%s,%s,%s,%s) "
                     "on conflict do nothing", (a.feed, a.kind, a.hour, a.day, a.detail))
    today = [a for a in ing.alerts if a.day == d]
    return dg.MaterializeResult(metadata={"day": d, "alerts_today": len(today),
                                          "pending": {f: s.pending for f, s in ing.state.items() if s.pending}})


@dg.asset_check(asset=raw_feeds, description="No feed has an open freshness or contract alert.")
def feeds_healthy(warehouse: Warehouse) -> dg.AssetCheckResult:
    conn = warehouse.conn()
    row = conn.execute("select state from ops.ingest_state where id = 1").fetchone()
    pending = {f: s["pending"] for f, s in (row[0]["feeds"] if row else {}).items() if s["pending"]}
    return dg.AssetCheckResult(passed=not pending, metadata={"pending_days": json.dumps(pending)})


@dg.asset(deps=[raw_feeds], group_name="decide",
          description="Resolve companies, link and classify articles, date signals, build golden records.")
def decisions(context: dg.AssetExecutionContext, warehouse: Warehouse, landing: Landing) -> dg.MaterializeResult:
    conn = warehouse.conn()
    row = conn.execute("select state from ops.ingest_state where id = 1").fetchone()
    ing = Ingestor(LandingSource(landing.path), PostgresLake(conn), design(), row[0] if row else None)
    customers = json.loads((Path(landing.path) / "crm.json").read_text())
    if ORCH["model_source"] == "claude":
        from signals.classify.claude import ClaudeModel

        cheap: Any = ClaudeModel("cheap")
        expensive: Any = ClaudeModel("expensive")
    else:
        answers = Path(landing.path) / "model_answers.json"
        cheap, expensive = ReplayModel(answers, "cheap"), ReplayModel(answers, "expensive")
    result = decide(PostgresLake(conn), ing.result(), customers, START, ing.next_day, design(), cheap, expensive)
    db.write_result(conn, result, "platform")
    return dg.MaterializeResult(metadata={"entities": len(result.resolution.members),
                                          "review_pairs": len(result.resolution_auto.review),
                                          "articles": len(result.decisions), "events": len(result.events)})


@dg.asset(deps=[decisions], group_name="marts", description="dbt build: staging views, marts and their tests.")
def dbt_marts(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    project = ROOT / ORCH["dbt_project"]
    dbt = os.environ.get("DBT_BIN", "dbt")
    out = subprocess.run([dbt, "build", "--project-dir", str(project), "--profiles-dir", str(project)],
                         capture_output=True, text=True)
    context.log.info(out.stdout[-4000:])
    if out.returncode != 0:
        raise dg.Failure(description="dbt build failed", metadata={"log": out.stdout[-4000:]})
    return dg.MaterializeResult(metadata={"tail": out.stdout.strip().splitlines()[-1]})


ingest_job = dg.define_asset_job("ingest_daily", selection=[raw_feeds], partitions_def=daily)
decide_job = dg.define_asset_job("decide_and_build", selection=[decisions, dbt_marts])

daily_schedule = dg.build_schedule_from_partitioned_job(ingest_job, hour_of_day=7, minute_of_hour=0)


@dg.run_status_sensor(run_status=dg.DagsterRunStatus.SUCCESS, monitored_jobs=[ingest_job],
                      request_job=decide_job)
def after_ingest(context: dg.RunStatusSensorContext) -> dg.RunRequest:
    return dg.RunRequest(run_key=context.dagster_run.run_id)


@dg.sensor(job=ingest_job, minimum_interval_seconds=300)
def redelivery(context: dg.SensorEvaluationContext, landing: Landing) -> Any:
    """A provider dropped a redelivery: run today's partition again so the backfill lands now."""
    files = sorted(str(p) for p in Path(landing.path).glob("*/redelivery/*.json"))
    seen = set(json.loads(context.cursor or "[]"))
    new = [f for f in files if f not in seen]
    if not new:
        return dg.SkipReason("no new redelivery")
    context.update_cursor(json.dumps(files))
    today = daily.get_last_partition_key()
    if today is None:
        return dg.SkipReason("no partition yet")
    return dg.RunRequest(run_key=f"redelivery-{len(files)}", partition_key=today)


defs = dg.Definitions(
    assets=[raw_feeds, decisions, dbt_marts],
    asset_checks=[feeds_healthy],
    jobs=[ingest_job, decide_job],
    schedules=[daily_schedule],
    sensors=[after_ingest, redelivery],
    resources={"warehouse": Warehouse(), "landing": Landing()},
)
