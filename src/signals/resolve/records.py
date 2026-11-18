"""Source records: one per company as each source sees it (a vendor id, a register number, a job-board domain, a CRM
row). Built from the raw layer; the latest delivery of a key wins inside one source."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from signals.ingest.lake import RawRow
from signals.normalize import domain_key

OLD_NAME = re.compile(r"Bisher:\s*(.+?)\.\s*Neu:")
FOUNDED = re.compile(r"Gründungsjahr\s+(\d{4})")


@dataclass
class SourceRecord:
    id: str                       # "<feed>:<key>"
    feed: str
    names: list[str]              # current name first, then older names
    domain: str = ""
    city: str = ""
    country: str = ""
    founded: int | None = None
    identifier: str = ""          # a key that can never belong to two companies (register number, CRM id)


def _latest(rows: list[RawRow]) -> dict[str, RawRow]:
    out: dict[str, RawRow] = {}
    for r in sorted(rows, key=lambda x: (x.delivery_day, x.loaded_hour, x.run_id)):
        out[r.key] = r
    return out


def vendor_records(rows: list[RawRow]) -> list[SourceRecord]:
    out = []
    for key, r in _latest(rows).items():
        p = r.payload
        out.append(SourceRecord(f"vendor_profiles:{key}", "vendor_profiles", [p.get("name") or ""],
                                domain_key(p.get("domain")), p.get("city") or "", p.get("country") or "",
                                p.get("founded_year")))
    return out


def register_records(rows: list[RawRow], use_aliases: bool) -> list[SourceRecord]:
    """A company in the register is (court, register number); every notice about it adds evidence."""
    by_company: dict[str, list[RawRow]] = {}
    for r in rows:
        p = r.payload
        by_company.setdefault(f"{p.get('court')}|{p.get('register_no')}", []).append(r)
    out = []
    for key, notices in by_company.items():
        notices.sort(key=lambda x: (x.delivery_day, x.loaded_hour))
        last = notices[-1].payload
        names = [last.get("company_name") or ""]
        founded = None
        for n in notices:
            text = n.payload.get("text") or ""
            if use_aliases:
                m = OLD_NAME.search(text)
                if m and m.group(1) not in names:
                    names.append(m.group(1))
                if n.payload.get("company_name") and n.payload["company_name"] not in names:
                    names.append(n.payload["company_name"])
            f = FOUNDED.search(text)
            founded = int(f.group(1)) if f else founded
        out.append(SourceRecord(f"register_notices:{key}", "register_notices", names, "", last.get("seat") or "",
                                last.get("country") or "", founded, identifier=f"register:{key}"))
    return out


def job_records(rows: list[RawRow]) -> list[SourceRecord]:
    domains = sorted({domain_key(r.payload.get("domain")) for r in rows if r.payload.get("domain")})
    return [SourceRecord(f"job_posts:{d}", "job_posts", [], d) for d in domains]


def crm_records(customers: list[dict[str, Any]]) -> list[SourceRecord]:
    return [SourceRecord(f"crm:{c['crm_id']}", "crm", [c["name"]], domain_key(c.get("domain")), c.get("city", ""),
                         c.get("country", ""), None, identifier=f"crm:{c['crm_id']}") for c in customers]


@dataclass
class RecordSet:
    records: list[SourceRecord] = field(default_factory=list)

    def by_id(self) -> dict[str, SourceRecord]:
        return {r.id: r for r in self.records}
