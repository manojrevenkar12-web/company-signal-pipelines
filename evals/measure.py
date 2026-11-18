"""Scores one pipeline run against the world's truth. Only evals/ may do this."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from evals.adapter import Truth
from evals.stats import rate
from signals.config import settings
from signals.ingest.lake import payload_hash
from signals.normalize import domain_key, name_key
from signals.pipeline import Result
from signals.resolve.match import Resolution
from world.generate import World

GONE = ("acquired", "shut_down")


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


def er_scores(res: Resolution, records: list[Any], truth: Truth) -> dict[str, float]:
    t = {r.id: truth.company(r.id) for r in records}
    cells = Counter((res.entity_of[r.id], t[r.id]) for r in records)
    tp = sum(_pairs(n) for (_, c), n in cells.items() if c is not None)
    pred = sum(_pairs(n) for n in Counter(res.entity_of[r.id] for r in records).values())
    true = sum(_pairs(n) for c, n in Counter(t.values()).items() if c is not None)
    return {"tp": tp, "pred": pred, "true": true}


def entity_truth(res: Resolution, truth: Truth) -> dict[str, str | None]:
    out = {}
    for e, members in res.members.items():
        c = Counter(x for x in (truth.company(m) for m in members) if x)
        out[e] = c.most_common(1)[0][0] if c else None
    return out


def measure(r: Result, world: World) -> dict[str, Any]:
    cfg = settings()
    truth = Truth(world)
    m: dict[str, Any] = {}
    start = world.start
    end = world.day(world.days)

    # ---------------------------------------------------------------- ingestion
    alerts = r.ingest.alerts
    outages = []
    for feed, s, length, kind in world.outages():
        cad = int(cfg["feeds"][feed]["cadence_days"])
        first_missed = next(d for d in range(s, s + length + cad) if d % cad == 0)
        h0 = first_missed * 24 + int(cfg["monitors"]["delivery_hour"])
        h1 = (s + length) * 24 + 24 * 7
        hits = [a for a in alerts if a.feed == feed and h0 <= a.hour <= h1 and a.kind != "duplicates"]
        detect = min((a.hour - h0 for a in hits), default=None)
        outages.append({"feed": feed, "kind": kind, "start_day": s, "days": length,
                        "hours_to_detect": detect, "by": hits[0].kind if hits else None})
    m["outages"] = outages
    windows = defaultdict(list)
    for o in outages:
        cad = int(cfg["feeds"][o["feed"]]["cadence_days"])
        windows[o["feed"]].append((o["start_day"] * 24, (o["start_day"] + o["days"] + cad) * 24 + 48))
    m["false_alerts"] = sum(1 for a in alerts if a.kind not in ("duplicates",)
                            and not any(lo <= a.hour <= hi for lo, hi in windows[a.feed]))
    det = [o["hours_to_detect"] for o in outages]
    m["max_hours_to_detect_outage"] = float("inf") if any(x is None for x in det) else max(det)
    complete, dup = {}, {}
    for feed in cfg["feeds"]:
        key = cfg["feeds"][feed]["key"]
        want = {(str(row[key]), payload_hash(row)) for (f, _), rows in world._deliveries.items() if f == feed
                for row in rows}
        have_rows = r.lake.rows(feed)
        have = {(x.key, x.hash) for x in have_rows}
        complete[feed] = len(want & have) / len(want)
        dup[feed] = len(have_rows) - len(have)
    m["completeness"] = complete
    m["raw_duplicates"] = sum(dup.values())
    m["raw_rows"] = sum(len(r.lake.rows(f)) for f in cfg["feeds"])

    # ---------------------------------------------------------------- entity resolution
    a = er_scores(r.resolution_auto, r.records, truth)
    f = er_scores(r.resolution, r.records, truth)
    m["er"] = {"auto": a, "final": f, "review_pairs": len(r.resolution_auto.review),
               "refused": len(r.resolution_auto.refused), "entities": len(r.resolution.members),
               "records": len(r.records)}
    m["er_pair_precision"] = rate(a["tp"], a["pred"])
    m["er_pair_recall"] = rate(a["tp"], a["true"])
    m["er_pair_recall_after_review"] = rate(f["tp"], f["true"])
    et = entity_truth(r.resolution, truth)

    # ---------------------------------------------------------------- linking and classification
    at = world.article_truth
    n = len(r.decisions)
    auto = [d for d in r.decisions.values() if d.decided_by in ("rule", "cheap", "expensive")]
    correct = [d for d in auto if d.label == at[d.url]["label"]]
    m["rel_precision"] = rate(len(correct), len(auto))
    m["rel_auto_share"] = len(auto) / n
    m["rel_review_share"] = sum(1 for d in r.decisions.values() if d.decided_by in ("review", "person")) / n
    m["rel_cost_per_record_eur"] = sum(d.cost_eur for d in r.decisions.values()) / n
    m["rel_accuracy_final"] = rate(sum(1 for d in r.decisions.values() if d.label == at[d.url]["label"]), n)
    m["rel_by_tier"] = dict(Counter(d.decided_by for d in r.decisions.values()))
    for sub, keep in (("ambiguous", lambda u: at[u]["ambiguous"]), ("german", lambda u: at[u]["german"])):
        s_auto = [d for d in auto if keep(d.url)]
        m[f"rel_precision_{sub}"] = rate(sum(1 for d in s_auto if d.label == at[d.url]["label"]), len(s_auto))
    linked = [lk for lk in r.links.values() if lk.status in ("linked", "linked_by_person")]
    good = [lk for lk in linked if et.get(lk.startup or "") == at[lk.url]["startup"]
            and et.get(lk.corporate or "") == at[lk.url]["corporate"]]
    m["link_precision"] = rate(len(good), len(linked))
    m["link_coverage"] = len(linked) / max(1, len(r.links))

    # ---------------------------------------------------------------- events
    true_events = [(e.company, e.kind, e.on) for e in world.events if start <= e.on < end]
    pred = [(et.get(ev.entity), ev.kind, ev.on) for ev in r.events]
    used: set[int] = set()
    errors: list[int] = []
    tp = 0
    for c, kind, on in sorted(pred, key=lambda x: x[2]):
        best = None
        for i, (tc, tk, ton) in enumerate(true_events):
            if i in used or tc != c or tk != kind:
                continue
            gap = abs((on - ton).days)
            if gap <= 60 and (best is None or gap < best[1]):
                best = (i, gap)
        if best:
            used.add(best[0])
            errors.append(best[1])
            tp += 1
    m["events"] = {"predicted": len(pred), "true": len(true_events), "matched": tp}
    m["event_precision"] = rate(tp, len(pred))
    m["event_recall"] = rate(tp, len(true_events))
    m["event_date_mae_days"] = sum(errors) / len(errors) if errors else float("nan")
    by_kind = {}
    for kind in ("funding", "acquisition", "shutdown", "headcount"):
        p_k = sum(1 for x in pred if x[1] == kind)
        t_k = sum(1 for x in true_events if x[1] == kind)
        by_kind[kind] = {"predicted": p_k, "true": t_k}
    m["events_by_kind"] = by_kind

    # ---------------------------------------------------------------- golden records
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    last_week = world.weeks - 1
    for e, fields in r.golden.items():
        c = world.companies.get(et.get(e) or "")
        if c is None:
            continue
        status = c.status if ((c.acquired_on and c.acquired_on <= end) or (c.shut_on and c.shut_on <= end)) \
            else "active"
        want = {"name": name_key(c.name), "domain": c.domain, "city": c.city, "country": c.country,
                "founded": c.founded, "headcount": c.headcount[last_week], "status": status}
        for fld, fv in fields.items():
            got = fv.value
            if fld == "name":
                ok = name_key(str(got)) == want["name"]
            elif fld == "domain":
                ok = domain_key(str(got)) == want["domain"]
            elif fld == "headcount":
                ok = abs(float(got) - want["headcount"]) <= 0.2 * max(want["headcount"], 1)
            else:
                ok = got == want[fld]
            acc[fld][0] += int(ok)
            acc[fld][1] += 1
    m["golden_accuracy"] = {k: v[0] / v[1] for k, v in acc.items() if v[1]}

    # ---------------------------------------------------------------- recommendations
    knowable = end - timedelta(days=7)
    gone = 0
    active_true = {c.id for c in world.companies.values() if c.kind == "startup" and not (
        (c.acquired_on and c.acquired_on <= end) or (c.shut_on and c.shut_on <= end))}
    rec_true = set()
    for e in r.recommendable:
        c = world.companies.get(et.get(e) or "")
        if c is None:
            continue
        rec_true.add(c.id)
        if (c.acquired_on and c.acquired_on <= knowable) or (c.shut_on and c.shut_on <= knowable):
            gone += 1
    m["gone_recommended"] = gone
    m["active_startups_recommendable"] = len(rec_true & active_true) / len(active_true)

    m["review_items"] = {"pairs": r.reviewed_pairs, "articles": r.reviewed_articles, "links": r.reviewed_links}
    m["stage_seconds"] = r.stage_seconds
    return m
