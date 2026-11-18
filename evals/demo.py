"""The production path end to end on Postgres: landing folder -> raw (idempotent) -> core -> dbt marts.

    python -m evals.demo --reset            # then: cd dbt && dbt build
Checks that the Postgres run gives the same decisions as the in-memory run of the evaluations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.drops import write_drops
from signals import db
from signals.config import design
from signals.ingest.lake import MemoryLake, PostgresLake
from signals.ingest.landing import LandingSource, ReplayModel
from signals.pipeline import run
from world.generate import World, load


def main(argv: list[str] | None = None) -> dict[str, int]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", default="landing")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args(argv)
    world = World(load("world"))
    days = args.days or world.days
    landing = Path(args.landing)
    write_drops(world, landing, days - 1)
    conn = db.connect()
    if args.reset:
        db.reset(conn)
    db.migrate(conn)
    customers = json.loads((landing / "crm.json").read_text())
    models = landing / "model_answers.json"
    d = design()
    src = LandingSource(landing)
    pg = run(src, customers, world.start, days, d, ReplayModel(models, "cheap"), ReplayModel(models, "expensive"),
             lake=PostgresLake(conn))
    db.write_result(conn, pg, "platform")
    mem = run(src, customers, world.start, days, d, ReplayModel(models, "cheap"), ReplayModel(models, "expensive"),
              lake=MemoryLake())
    same = {"entities": len(pg.resolution.members) == len(mem.resolution.members),
            "events": len(pg.events) == len(mem.events),
            "alerts": [(a.feed, a.kind, a.hour) for a in pg.ingest.alerts]
            == [(a.feed, a.kind, a.hour) for a in mem.ingest.alerts]}
    counts = {t: int(conn.execute(f"select count(*) from {t}").fetchone()[0])  # noqa: S608
              for t in ("raw.record", "raw.load_run", "core.entity", "core.article", "core.event", "ops.alert")}
    print(json.dumps({"same_as_memory": same, "rows": counts}, indent=1))
    if not all(same.values()):
        raise SystemExit("Postgres and in-memory runs disagree")
    return counts


if __name__ == "__main__":
    main()
