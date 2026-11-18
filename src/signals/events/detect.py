"""Signals: funding, acquisition, shutdown and headcount change, each dated by the earliest credible evidence.

Evidence carries two dates: the date it states (a contract date in a register notice, an announcement date, a
publication date) and the day the pipeline first saw it. The platform dates an event by the earliest stated date; the
status quo dates it by the day it was ingested, which is how a round announced in June appears as a July signal.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from signals.classify.cascade import Decision
from signals.classify.link import Link
from signals.ingest.lake import RawRow
from signals.normalize import domain_key

GERMAN_DATE = re.compile(r"(?:vom|am)\s+(\d{2})\.(\d{2})\.(\d{4})")


@dataclass
class Evidence:
    entity: str
    kind: str              # funding | acquisition | shutdown | headcount
    stated: date | None    # what the evidence says
    seen: date             # when the pipeline first had it
    source: str
    ref: str


@dataclass
class Event:
    entity: str
    kind: str
    on: date
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        return sorted({e.source for e in self.evidence})


def _seen(start: date, r: RawRow) -> date:
    return start + timedelta(hours=r.loaded_hour)


def vendor_evidence(rows: list[RawRow], entity_of: dict[str, str], start: date) -> list[Evidence]:
    out: list[Evidence] = []
    first_round: dict[tuple[str, str, int], Evidence] = {}
    first_status: dict[tuple[str, str], Evidence] = {}
    for r in sorted(rows, key=lambda x: x.loaded_hour):
        e = entity_of.get(f"vendor_profiles:{r.key}")
        if not e:
            continue
        p = r.payload
        for rd in p.get("funding_rounds") or []:
            k = (e, str(rd.get("round")), int(rd.get("amount_eur") or 0))
            if k not in first_round:
                stated = date.fromisoformat(rd["announced_on"]) if rd.get("announced_on") else None
                first_round[k] = Evidence(e, "funding", stated, _seen(start, r), "vendor_profiles",
                                          f"{rd.get('round')} {rd.get('amount_eur')}")
        status = p.get("status")
        if status in ("acquired", "shut_down") and (e, status) not in first_status:
            first_status[(e, status)] = Evidence(e, "acquisition" if status == "acquired" else "shutdown", None,
                                                 _seen(start, r), "vendor_profiles", f"status {status}")
    out.extend(first_round.values())
    out.extend(first_status.values())
    return out


def register_evidence(rows: list[RawRow], entity_of: dict[str, str], start: date) -> list[Evidence]:
    out = []
    kinds = {"verschmelzung": "acquisition", "liquidation": "shutdown", "insolvenz": "shutdown"}
    for r in rows:
        p = r.payload
        kind = kinds.get(str(p.get("kind")))
        e = entity_of.get(f"register_notices:{p.get('court')}|{p.get('register_no')}")
        if not kind or not e:
            continue
        m = GERMAN_DATE.search(p.get("text") or p.get("bekanntmachung") or "")
        stated = date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
        out.append(Evidence(e, kind, stated, _seen(start, r), "register_notices", r.key))
    return out


def news_evidence(rows: list[RawRow], decisions: dict[str, Decision], links: dict[str, Link],
                  start: date) -> list[Evidence]:
    out = []
    for r in rows:
        d, link = decisions.get(r.key), links.get(r.key)
        if not d or not link or not link.startup or d.label != "acquisition" or d.decided_by == "review":
            continue
        stated = date.fromisoformat(r.payload["published_on"]) if r.payload.get("published_on") else None
        out.append(Evidence(link.startup, "acquisition", stated, _seen(start, r), "news_mentions", r.key))
    return out


def job_series(rows: list[RawRow], entity_of: dict[str, str], weeks: int, start: date) -> dict[str, dict[int, int]]:
    """Open posts per entity per week. A week no file arrived for is absent, not zero."""
    series: dict[str, dict[int, int]] = defaultdict(dict)
    for r in rows:
        p = r.payload
        e = entity_of.get(f"job_posts:{domain_key(p.get('domain'))}")
        posts = p.get("open_posts")
        if e is None or posts is None:
            continue
        w = (date.fromisoformat(str(p.get("week_start"))) - start).days // 7
        if w < weeks:
            series[e][w] = series[e].get(w, 0) + int(posts)
    return series


def headcount_evidence(series: dict[str, dict[int, int]], weeks: int, start: date, design: dict[str, Any],
                       cfg: dict[str, Any], missing_weeks: set[int]) -> list[Evidence]:
    """A sustained change in open job posts: the mean of four weeks against the four before."""
    s = cfg["signals"]
    k = int(s["headcount_min_weeks"])
    out = []
    for e, by_week in series.items():
        vals: list[float | None] = []
        for w in range(weeks):
            if w in by_week:
                vals.append(float(by_week[w]))
            elif design["missing_weeks"] == "zero" and w in missing_weeks:
                vals.append(0.0)
            else:
                vals.append(None)
        best: tuple[float, int] | None = None
        for w in range(k, weeks - k + 1):
            before = [v for v in vals[w - k:w] if v is not None]
            after = [v for v in vals[w:w + k] if v is not None]
            if len(before) < k - 1 or len(after) < k - 1:
                continue
            mb, ma = statistics.mean(before), statistics.mean(after)
            if mb < float(s["headcount_min_posts"]):
                continue
            change = abs(ma - mb) / mb
            if change >= float(s["headcount_change_min"]) and (best is None or change > best[0]):
                best = (change, w)
        if best:
            on = start + timedelta(days=7 * best[1])
            seen = start + timedelta(days=7 * min(weeks - 1, best[1] + k))
            out.append(Evidence(e, "headcount", on, seen, "job_posts", f"{best[0]:+.0%} at week {best[1]}"))
    return out


def dark_evidence(series: dict[str, dict[int, int]], weeks: int, start: date, cfg: dict[str, Any],
                  feed_missing_weeks: set[int]) -> list[Evidence]:
    """A company that had a jobs page every week and then vanished from the jobs feed, while the feed itself kept
    arriving, has most likely shut down: its site is gone."""
    k = int(cfg["signals"]["dark_weeks"])
    delivered = [w for w in range(weeks) if w not in feed_missing_weeks]
    out = []
    for e, by_week in series.items():
        if not by_week:
            continue
        last = max(by_week)
        after = [w for w in delivered if w > last]
        if len(after) >= k:
            out.append(Evidence(e, "shutdown", start + timedelta(days=7 * (last + 1)),
                                start + timedelta(days=7 * after[k - 1] + 1), "job_posts",
                                f"no jobs page since week {last + 1}"))
    return out


def merge(evidence: list[Evidence], design: dict[str, Any], cfg: dict[str, Any]) -> list[Event]:
    """One event per company, kind and window; dated by the earliest stated date (or first sight)."""
    def when(ev: Evidence) -> date:
        if design["event_dates"] == "evidence" and ev.stated is not None:
            return min(ev.stated, ev.seen)
        return ev.seen

    if not design["dedupe_events"]:
        return [Event(ev.entity, ev.kind, when(ev), [ev]) for ev in evidence]
    window = timedelta(days=int(cfg["signals"]["event_merge_days"]))
    groups: dict[tuple[str, str], list[Evidence]] = defaultdict(list)
    for ev in evidence:
        groups[(ev.entity, ev.kind)].append(ev)
    events = []
    for (entity, kind), evs in groups.items():
        evs.sort(key=when)
        # acquisitions and shutdowns happen once; funding rounds and headcount changes can repeat
        if kind in ("acquisition", "shutdown"):
            events.append(Event(entity, kind, when(evs[0]), evs))
            continue
        current: Event | None = None
        for ev in evs:
            if current and when(ev) - current.on <= window:
                current.evidence.append(ev)
            else:
                current = Event(entity, kind, when(ev), [ev])
                events.append(current)
    return events
