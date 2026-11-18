"""Vendor evaluation (what each feed costs per correct datapoint) and the search benchmark."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from evals.adapter import Truth
from evals.measure import entity_truth
from evals.stats import rate
from signals.config import settings
from signals.normalize import name_key
from signals.pipeline import Result
from signals.search import NameIndex
from world.generate import World, _h


def vendor_table(r: Result, world: World) -> list[dict[str, Any]]:
    cfg = settings()["feeds"]
    truth = Truth(world)
    covered: dict[str, set[str]] = defaultdict(set)
    for rec in r.records:
        c = truth.company(rec.id)
        if c and rec.feed in cfg:
            covered[rec.feed].add(c)
    correct: dict[str, int] = defaultdict(int)
    last_week = world.weeks - 1
    for rec in r.records:
        c = world.companies.get(truth.company(rec.id) or "")
        if c is None:
            continue
        if rec.feed == "vendor_profiles":
            correct[rec.feed] += sum([name_key(rec.names[0]) == name_key(c.name), rec.domain == c.domain,
                                      rec.city == c.city, rec.country == c.country, rec.founded == c.founded])
        elif rec.feed == "register_notices":
            correct[rec.feed] += sum([name_key(rec.names[0]) == name_key(c.name), rec.city == c.city,
                                      rec.country == c.country, rec.founded == c.founded])
    for row in r.lake.rows("vendor_profiles"):
        c = world.companies.get(world.source_truth.get(("vendor_profiles", row.key)) or "")
        hc = row.payload.get("headcount")
        if c and hc is not None and abs(hc - c.headcount[min(row.delivery_day // 7, last_week)]) <= 0.2 * max(
                1, c.headcount[min(row.delivery_day // 7, last_week)]):
            correct["vendor_profiles"] += 1
    correct["job_posts"] = sum(1 for row in r.lake.rows("job_posts") if row.payload.get("open_posts") is not None)
    et = entity_truth(r.resolution, truth)
    at = world.article_truth
    for url, d in r.decisions.items():
        lk = r.links.get(url)
        if lk and lk.startup and et.get(lk.startup) == at[url]["startup"] and d.label == at[url]["label"]:
            correct["news_mentions"] += 1
    others = {f: set().union(*(covered[g] for g in covered if g != f)) for f in covered}
    out = []
    for feed, fc in cfg.items():
        delivered = sum(run.rows for run in r.lake.runs if run.feed == feed)
        spend = delivered * float(fc["cost_per_record_eur"])
        out.append({"feed": feed, "records_billed": delivered, "spend_eur": round(spend, 2),
                    "companies": len(covered.get(feed, set())),
                    "only_here": len(covered.get(feed, set()) - others.get(feed, set())),
                    "correct_datapoints": correct[feed],
                    "eur_per_correct_datapoint": round(spend / correct[feed], 5) if correct[feed] else None})
    return out


def search_benchmark(r: Result, world: World, n: int = 600) -> dict[str, Any]:
    truth = Truth(world)
    et = entity_truth(r.resolution, truth)
    by_id = {x.id: x for x in r.records}
    names = {}
    for e, members in r.resolution.members.items():
        g = r.golden.get(e, {}).get("name")
        ns = ([str(g.value)] if g else []) + [nm for m in members for nm in by_id[m].names if nm]
        if ns:
            names[e] = ns
    index = NameIndex(names)
    startups = [c for c in world.companies.values() if c.kind == "startup"]
    picked = sorted(startups, key=lambda c: _h(world.seed, c.id, "query"))[:n]
    queries = [(world._variant(c, "news_mentions", ("query", c.id)), c.id) for c in picked]
    out: dict[str, Any] = {"queries": len(queries)}
    for method in ("exact", "normalised", "fuzzy"):
        at1 = at5 = 0
        for q, want in queries:
            got = [et.get(e) for e in index.search(q, 5, method)]
            at1 += int(bool(got) and got[0] == want)
            at5 += int(want in got)
        out[method] = {"recall_at_1": rate(at1, len(queries)), "recall_at_5": rate(at5, len(queries))}
    out["examples"] = [q for q, _ in queries[:8]]
    return out
