"""Writes what the simulated providers deliver into a landing folder, up to a given day, so the production path
(LandingSource -> PostgresLake -> core -> dbt -> Hasura/API) runs on the same luck as the evaluations.

    python -m evals.drops --landing landing --through 83
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from world.generate import World, load


def write_drops(world: World, landing: Path, through: int) -> int:
    n = 0
    for feed in ("vendor_profiles", "register_notices", "news_mentions", "job_posts"):
        (landing / feed / "redelivery").mkdir(parents=True, exist_ok=True)
        for d in range(through + 1):
            rows = world.fetch(feed, d)
            if rows is not None:
                (landing / feed / f"{d:03d}.json").write_text(json.dumps(rows))
                n += 1
            again = world.backfill(feed, d, through)
            if again is not None and rows != again:
                (landing / feed / "redelivery" / f"{d:03d}.json").write_text(json.dumps(again))
    (landing / "crm.json").write_text(json.dumps(world.customers()))
    answers: dict[str, dict[str, list[object]]] = {"cheap": {}, "expensive": {}}
    for url in world.article_truth:
        for tier in answers:
            answers[tier][url] = list(world.llm_label(url, tier))
    (landing / "model_answers.json").write_text(json.dumps(answers))
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", default="landing")
    ap.add_argument("--through", type=int, default=83)
    ap.add_argument("--world", default="world")
    args = ap.parse_args()
    w = World(load(args.world))
    print(write_drops(w, Path(args.landing), args.through), "files")


if __name__ == "__main__":
    main()
