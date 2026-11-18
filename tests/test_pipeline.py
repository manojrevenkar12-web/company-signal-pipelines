"""The platform end to end on the dev world, and the held-out lock."""

import json

import pytest

from evals import run as evalrun
from evals.adapter import SimModel, SimReviewer
from evals.measure import measure
from signals.config import design, gates
from signals.pipeline import run


@pytest.fixture(scope="module")
def platform(world):
    r = run(world, world.customers(), world.start, world.days, design(), SimModel(world, "cheap"),
            SimModel(world, "expensive"), SimReviewer(world))
    return r, measure(r, world)


def test_the_platform_passes_its_gates_on_one_dev_seed(platform):
    _, m = platform
    row = {k: (v if isinstance(v, dict) else {"mean": v}) for k, v in m.items()}
    failed = [g for g in evalrun.judge(row) if not g["passed"]]
    assert not failed, failed


def test_every_outage_is_detected_and_nothing_else_alerts(platform):
    _, m = platform
    assert all(o["hours_to_detect"] is not None for o in m["outages"])
    assert m["false_alerts"] == 0
    assert min(m["completeness"].values()) == 1.0


def test_review_queues_stay_small(platform):
    r, _ = platform
    assert len(r.resolution_auto.review) < 0.05 * len(r.records)
    assert sum(1 for d in r.decisions.values() if d.decided_by in ("review", "person")) < 0.02 * len(r.decisions)


def test_the_status_quo_fails_where_the_platform_passes(world):
    spec = evalrun.designs()["status_quo"]
    d = design({k: v for k, v in spec.items() if k != "label"})
    m = measure(run(world, world.customers(), world.start, world.days, d, SimModel(world, "cheap"),
                    SimModel(world, "expensive")), world)
    assert m["max_hours_to_detect_outage"] == float("inf")      # a schema drift is never noticed
    assert m["er_pair_precision"]["rate"] < 0.9
    assert m["event_date_mae_days"] > 7
    assert m["gone_recommended"] > 0


def test_the_held_out_world_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(evalrun, "REPORTS", tmp_path)
    (tmp_path / "heldout.lock").write_text("run before\n")
    assert evalrun.main(["--heldout"]) == 2
    assert not (tmp_path / "heldout.json").exists()


def test_gates_are_judged_on_the_worse_end_of_the_interval():
    row = {g["metric"]: {"mean": 0.0} for g in gates().values()}
    row["er_pair_precision"] = {"rate": 0.99, "low": 0.97, "high": 0.995}
    row["er_pair_recall"] = {"rate": 0.99, "low": 0.98, "high": 0.995}
    row["rel_precision"] = {"rate": 0.99, "low": 0.98, "high": 0.995}
    out = {g["gate"]: g for g in evalrun.judge(row)}
    assert not out["er_precision"]["passed"]                    # 0.99 observed, but the interval reaches 0.97
    assert json.dumps(out)
