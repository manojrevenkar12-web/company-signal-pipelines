"""Every design on the same dev worlds, the gates, and (once) the held-out world.

    python -m evals.run            # dev seeds, writes reports/dev.json
    python -m evals.run --heldout  # the held-out world, once; writes reports/heldout.json and a lock
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

from evals.adapter import SimModel, SimReviewer
from evals.extras import search_benchmark, vendor_table
from evals.measure import measure
from evals.stats import mean_ci, pool
from signals.config import design, gates
from signals.pipeline import run
from world.generate import World, load

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RATES = ["er_pair_precision", "er_pair_recall", "er_pair_recall_after_review", "rel_precision",
         "rel_accuracy_final", "rel_precision_ambiguous", "rel_precision_german", "link_precision",
         "event_precision", "event_recall"]
SCALARS = ["rel_cost_per_record_eur", "rel_auto_share", "rel_review_share", "link_coverage", "event_date_mae_days",
           "gone_recommended", "false_alerts", "raw_duplicates", "max_hours_to_detect_outage",
           "active_startups_recommendable"]


def designs() -> dict[str, dict[str, Any]]:
    with open(ROOT / "config" / "designs.toml", "rb") as f:
        return tomllib.load(f)


def run_world(cfg: dict[str, Any], names: list[str]) -> dict[str, Any]:
    world = World(cfg)
    customers = world.customers()
    out: dict[str, Any] = {}
    for name in names:
        spec = designs()[name]
        d = design({k: v for k, v in spec.items() if k != "label"})
        t = time.perf_counter()
        res = run(world, customers, world.start, world.days, d, SimModel(world, "cheap"),
                  SimModel(world, "expensive"), SimReviewer(world))
        m = measure(res, world)
        m["seconds"] = time.perf_counter() - t
        if name == "platform":
            m["vendors"] = vendor_table(res, world)
            m["search"] = search_benchmark(res, world)
        out[name] = m
    return out


def summarise(per_seed: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    s: dict[str, Any] = {}
    for name in names:
        runs = [x[name] for x in per_seed]
        row: dict[str, Any] = {"label": designs()[name]["label"]}
        for k in RATES:
            row[k] = pool([r[k] for r in runs])
        for k in SCALARS:
            vals = [float(r[k]) for r in runs]
            row[k] = {"mean": (sum(vals) / len(vals)) if all(math.isfinite(v) for v in vals) else float("inf"),
                      "ci": mean_ci(vals) if all(math.isfinite(v) for v in vals) else None,
                      "per_seed": vals}
        row["outages"] = [r["outages"] for r in runs]
        row["completeness"] = {f: sum(r["completeness"][f] for r in runs) / len(runs)
                               for f in runs[0]["completeness"]}
        row["golden_accuracy"] = {f: sum(r["golden_accuracy"].get(f, 0) for r in runs) / len(runs)
                                  for f in runs[0]["golden_accuracy"]}
        row["review_items"] = {k: sum(r["review_items"][k] for r in runs) / len(runs)
                               for k in runs[0]["review_items"]}
        row["rel_by_tier"] = runs[0]["rel_by_tier"]
        row["events_by_kind"] = runs[0]["events_by_kind"]
        row["seconds"] = sum(r["seconds"] for r in runs) / len(runs)
        if "vendors" in runs[0]:
            row["vendors"] = runs[0]["vendors"]
            row["search"] = {m: {k: pool([r["search"][m][k] for r in runs]) for k in ("recall_at_1", "recall_at_5")}
                             for m in ("exact", "normalised", "fuzzy")}
            row["search_examples"] = runs[0]["search"]["examples"]
        s[name] = row
    return s


def judge(row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for gid, g in gates().items():
        v = row[g["metric"]]
        if "low" in v:   # a rate: the worse end of its interval
            value = v["low"] if g["direction"] == "min" else v["high"]
        else:
            value = v["mean"]
        ok = value >= g["threshold"] if g["direction"] == "min" else value <= g["threshold"]
        out.append({"gate": gid, "metric": g["metric"], "direction": g["direction"], "threshold": g["threshold"],
                    "value": value, "passed": bool(ok), "why": g["why"]})
    return out


def fingerprint() -> str:
    h = hashlib.sha256()
    for p in sorted([*ROOT.glob("src/signals/**/*.py"), *ROOT.glob("config/*.toml"), *ROOT.glob("world/*.py")]):
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _clean(x: Any) -> Any:
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout", action="store_true")
    ap.add_argument("--seeds", type=int, nargs="*", default=None)
    ap.add_argument("--designs", nargs="*", default=None)
    args = ap.parse_args(argv)
    names = args.designs or list(designs())
    REPORTS.mkdir(exist_ok=True)
    if args.heldout:
        lock = REPORTS / "heldout.lock"
        if lock.exists():
            print(f"held-out world already run ({lock.read_text().strip()}); it is run once.", file=sys.stderr)
            return 2
        cfg = load("heldout")
        per_seed = [run_world(cfg, names)]
        summary = summarise(per_seed, names)
        report = {"world": "heldout", "seeds": [cfg["seed"]], "fingerprint": fingerprint(), "designs": summary,
                  "gates": judge(summary["platform"]), "per_seed": per_seed}
        (REPORTS / "heldout.json").write_text(json.dumps(_clean(report), indent=1, default=str))
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT).stdout.strip()
        lock.write_text(f"run {time.strftime('%Y-%m-%d')} at commit {commit or 'uncommitted'}, "
                        f"code fingerprint {report['fingerprint']}\n")
    else:
        base = load("world")
        seeds = args.seeds or base["dev_seeds"]
        per_seed = []
        for seed in seeds:
            cfg = dict(base, seed=seed)
            per_seed.append(run_world(cfg, names))
            print(f"seed {seed} done", file=sys.stderr)
        summary = summarise(per_seed, names)
        report = {"world": "dev", "seeds": seeds, "fingerprint": fingerprint(), "designs": summary,
                  "gates": judge(summary["platform"]) if "platform" in summary else [], "per_seed": per_seed}
        (REPORTS / "dev.json").write_text(json.dumps(_clean(report), indent=1, default=str))
    for g in report["gates"]:
        print(f"{'PASS' if g['passed'] else 'FAIL'} {g['gate']}: {g['value']} ({g['direction']} {g['threshold']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
