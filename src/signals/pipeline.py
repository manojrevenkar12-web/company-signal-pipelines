"""One run of the platform end to end, the same code for every design: ingest with checks and backfills, resolve
companies, link and classify articles, collect evidence into dated signals, build golden records and the
recommendable view. People decide what lands in the review queues; `reviewer` stands in for them when given."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol

from signals.classify.cascade import Decision, Model, classify
from signals.classify.link import Gazetteer, Link
from signals.config import settings
from signals.events.detect import (
    Event,
    Evidence,
    dark_evidence,
    headcount_evidence,
    job_series,
    merge,
    news_evidence,
    register_evidence,
    vendor_evidence,
)
from signals.golden import FieldValue, Observation, golden, observations
from signals.ingest.lake import Lake, MemoryLake
from signals.ingest.runner import IngestResult, Source, run_ingest
from signals.resolve.match import Pair, Resolution, apply_decisions, resolve
from signals.resolve.records import SourceRecord, crm_records, job_records, register_records, vendor_records

FEEDS = ["vendor_profiles", "register_notices", "news_mentions", "job_posts"]


class Reviewer(Protocol):
    def same_company(self, a: str, b: str) -> bool | None: ...

    def relationship(self, url: str) -> str | None: ...

    def which_company(self, url: str, candidates: dict[str, list[str]]) -> str | None: ...


@dataclass
class Result:
    design: dict[str, Any]
    start: date
    days: int
    lake: Lake
    ingest: IngestResult
    records: list[SourceRecord]
    resolution_auto: Resolution
    resolution: Resolution
    links: dict[str, Link]
    decisions: dict[str, Decision]
    evidence: list[Evidence]
    events: list[Event]
    golden: dict[str, dict[str, FieldValue]]
    startups: set[str]
    recommendable: list[str]
    reviewed_pairs: int = 0
    reviewed_articles: int = 0
    reviewed_links: int = 0
    stage_seconds: dict[str, float] = field(default_factory=dict)


def run(source: Source, customers: list[dict[str, Any]], start: date, days: int, design: dict[str, Any],
        cheap: Model, expensive: Model, reviewer: Reviewer | None = None, lake: Lake | None = None) -> Result:
    lake = lake or MemoryLake()
    t0 = time.perf_counter()
    ingest = run_ingest(source, lake, days, design)
    seconds = time.perf_counter() - t0
    r = decide(lake, ingest, customers, start, days, design, cheap, expensive, reviewer)
    r.stage_seconds = {"ingest": seconds, **r.stage_seconds}
    return r


def decide(lake: Lake, ingest: IngestResult, customers: list[dict[str, Any]], start: date, days: int,
           design: dict[str, Any], cheap: Model, expensive: Model, reviewer: Reviewer | None = None) -> Result:
    """Everything after the raw layer, from what the raw layer holds."""
    tick = time.perf_counter
    cfg = settings()
    t: dict[str, float] = {}
    rows = {f: lake.rows(f) for f in FEEDS}

    t0 = tick()
    records = (vendor_records(rows["vendor_profiles"]) + register_records(rows["register_notices"],
                                                                           design["er_use_aliases"])
               + job_records(rows["job_posts"]) + crm_records(customers))
    auto = resolve(records, design, cfg)
    res = auto
    reviewed_pairs = 0
    if reviewer is not None and design["review_queue"] and auto.review:
        answers = {(p.a, p.b): reviewer.same_company(p.a, p.b) for p in auto.review}
        same = {k for k, v in answers.items() if v}
        reviewed_pairs = sum(1 for v in answers.values() if v is not None)
        res = apply_decisions(auto, records, same)
    t["resolve"] = tick() - t0

    t0 = tick()
    by_id = {r.id: r for r in records}
    corporates: dict[str, list[str]] = {}
    startups: dict[str, list[str]] = {}
    domains: dict[str, str] = {}
    for e, members in res.members.items():
        names = [n for m in members for n in by_id[m].names if n]
        target = corporates if any(by_id[m].feed == "crm" for m in members) else startups
        target[e] = names
        for m in members:
            if by_id[m].domain:
                domains[by_id[m].domain] = e
    gaz = Gazetteer(corporates, startups, domains)
    links: dict[str, Link] = {}
    decisions: dict[str, Decision] = {}
    reviewed_articles = 0
    reviewed_links = 0
    max_cands = int(cfg["linking"]["review_max_candidates"])
    latest_article = {r.key: r for r in rows["news_mentions"]}
    for url, r in latest_article.items():
        art = dict(r.payload)
        lk = gaz.link(art)
        dec = classify(art, design, cfg, cheap, expensive)
        # which startup an article is about matters only if it says something about a relationship
        if lk.status == "ambiguous" and reviewer is not None and design["review_queue"] \
                and len(lk.candidates) <= max_cands and dec.label != "none":
            pick = reviewer.which_company(url, {c: res.members[c] for c in lk.candidates})
            reviewed_links += 1
            if pick:
                lk = Link(url, lk.corporate, pick, "linked_by_person", lk.candidates)
        links[url] = lk
        if dec.decided_by == "review" and reviewer is not None:
            answer = reviewer.relationship(url)
            if answer is not None:
                dec = Decision(url, answer, "person", 1.0, dec.cost_eur, dec.steps + ">person")
                reviewed_articles += 1
        decisions[url] = dec
    t["classify"] = tick() - t0

    t0 = tick()
    weeks = days // 7
    missing_weeks = {d // 7 for d in ingest.missing_days.get("job_posts", [])}
    if not design["backfill"]:
        missing_weeks |= {d // 7 for d in ingest.backfilled_days.get("job_posts", [])}
    series = job_series(rows["job_posts"], res.entity_of, weeks, start)
    evidence = (vendor_evidence(rows["vendor_profiles"], res.entity_of, start)
                + register_evidence(rows["register_notices"], res.entity_of, start)
                + news_evidence(rows["news_mentions"], decisions, links, start)
                + headcount_evidence(series, weeks, start, design, cfg, missing_weeks)
                + (dark_evidence(series, weeks, start, cfg, missing_weeks) if design["dark_signal"] else []))
    events = merge(evidence, design, cfg)
    today = start + timedelta(days=days)
    obs = observations(rows, res.entity_of, customers, decisions, links, start)
    obs += [Observation(ev.entity, "status", "shut_down", ev.source, ev.seen) for ev in evidence
            if ev.kind == "shutdown" and ev.source == "job_posts"]
    gold = golden(obs, design, cfg, today)
    recommendable = []
    for e in startups:
        status = gold.get(e, {}).get("status")
        if design["status_filter"] and status is not None and status.value in ("acquired", "shut_down"):
            continue
        if "name" in gold.get(e, {}):
            recommendable.append(e)
    t["signals"] = tick() - t0
    return Result(design, start, days, lake, ingest, records, auto, res, links, decisions, evidence, events, gold,
                  set(startups), sorted(recommendable), reviewed_pairs, reviewed_articles, reviewed_links, t)


__all__ = ["run", "Result", "Pair", "Reviewer"]
