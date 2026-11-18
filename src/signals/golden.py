"""The golden record: one value per company and field, with the source, the day it was observed and why it won.

priority: the source order in config [fields], the freshest value within a source, values older than max_age_days
only when nothing fresher exists. A terminal status (acquired, shut down) from any trusted source beats 'active',
because companies do not come back from either. last_write: whichever source wrote last wins (the status quo).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from signals.classify.cascade import Decision
from signals.classify.link import Link
from signals.ingest.lake import RawRow
from signals.normalize import domain_key

FIELDS = ["name", "domain", "city", "country", "founded", "headcount", "status"]


@dataclass
class Observation:
    entity: str
    field: str
    value: Any
    source: str
    observed: date


@dataclass
class FieldValue:
    entity: str
    field: str
    value: Any
    source: str
    observed: date
    why: str


def observations(lake_rows: dict[str, list[RawRow]], entity_of: dict[str, str], customers: list[dict[str, Any]],
                 decisions: dict[str, Decision], links: dict[str, Link], start: date) -> list[Observation]:
    obs: list[Observation] = []

    def when(r: RawRow) -> date:
        return start + timedelta(hours=r.loaded_hour)

    for r in lake_rows.get("vendor_profiles", []):
        e = entity_of.get(f"vendor_profiles:{r.key}")
        if not e:
            continue
        p = r.payload
        hc = p.get("headcount")
        for f, v in (("name", p.get("name")), ("domain", domain_key(p.get("domain"))), ("city", p.get("city")),
                     ("country", p.get("country")), ("founded", p.get("founded_year")), ("headcount", hc),
                     ("status", p.get("status"))):
            if v not in (None, ""):
                obs.append(Observation(e, f, v, "vendor_profiles", when(r)))
    status_of = {"verschmelzung": "acquired", "liquidation": "shut_down", "insolvenz": "shut_down"}
    for r in lake_rows.get("register_notices", []):
        p = r.payload
        e = entity_of.get(f"register_notices:{p.get('court')}|{p.get('register_no')}")
        if not e:
            continue
        for f, v in (("name", p.get("company_name")), ("city", p.get("seat")), ("country", p.get("country")),
                     ("status", status_of.get(str(p.get("kind"))))):
            if v not in (None, ""):
                obs.append(Observation(e, f, v, "register_notices", when(r)))
    for c in customers:
        e = entity_of.get(f"crm:{c['crm_id']}")
        if e:
            obs.append(Observation(e, "name", c["name"], "crm", start))
            obs.append(Observation(e, "domain", domain_key(c["domain"]), "crm", start))
    for r in lake_rows.get("news_mentions", []):
        d, link = decisions.get(r.key), links.get(r.key)
        if d and link and link.startup and d.label == "acquisition" and d.decided_by != "review":
            obs.append(Observation(link.startup, "status", "acquired", "news_mentions", when(r)))
    return obs


def golden(obs: list[Observation], design: dict[str, Any], cfg: dict[str, Any], today: date) -> dict[
        str, dict[str, FieldValue]]:
    by: dict[tuple[str, str], list[Observation]] = {}
    for o in obs:
        by.setdefault((o.entity, o.field), []).append(o)
    pri = cfg["fields"]
    max_age = pri["max_age_days"]
    out: dict[str, dict[str, FieldValue]] = {}
    for (e, f), os_ in by.items():
        if design["provenance"] == "last_write":
            o = max(os_, key=lambda x: x.observed)
            out.setdefault(e, {})[f] = FieldValue(e, f, o.value, o.source, o.observed, "last write")
            continue
        order = list(pri.get(f, []))
        def rank(o: Observation, order: list[str] = order) -> tuple[int, int]:
            src = order.index(o.source) if o.source in order else len(order)
            return (src, -o.observed.toordinal())
        if f == "status":
            terminal = [o for o in os_ if o.value in ("acquired", "shut_down")]
            if terminal:
                o = min(terminal, key=rank)
                out.setdefault(e, {})[f] = FieldValue(e, f, o.value, o.source, o.observed,
                                                      "terminal status from " + o.source)
                continue
        limit = int(max_age.get(f, 3650))
        fresh = [o for o in os_ if (today - o.observed).days <= limit] or os_
        o = min(fresh, key=rank)
        out.setdefault(e, {})[f] = FieldValue(e, f, o.value, o.source, o.observed,
                                              f"priority {order.index(o.source) + 1 if o.source in order else '-'}")
    return out
