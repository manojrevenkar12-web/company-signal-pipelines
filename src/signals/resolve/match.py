"""Entity resolution: block, score, merge what is certain, queue what is doubtful.

Identifiers decide and names propose: an equal normalised domain decides a match; two different register numbers or
CRM ids are never merged, even through a chain of other records; a name only proposes a score.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from rapidfuzz import fuzz

from signals.normalize import compact_key, name_key, transliterate
from signals.resolve.records import SourceRecord


@dataclass
class Pair:
    a: str
    b: str
    score: float
    reason: str


@dataclass
class Resolution:
    entity_of: dict[str, str]                 # record id -> entity id
    members: dict[str, list[str]]             # entity id -> record ids
    review: list[Pair] = field(default_factory=list)
    merged: list[Pair] = field(default_factory=list)
    refused: list[Pair] = field(default_factory=list)   # would have joined two identifiers


class _UF:
    def __init__(self, ids: list[str], idents: dict[str, str]):
        self.p = {i: i for i in ids}
        self.idents: dict[str, set[str]] = {i: ({idents[i]} if idents.get(i) else set()) for i in ids}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if self.idents[ra] and self.idents[rb] and self.idents[ra] != self.idents[rb]:
            return False
        self.p[rb] = ra
        self.idents[ra] |= self.idents[rb]
        return True


def _keys(r: SourceRecord, translit: bool) -> set[str]:
    """Blocking keys. Several per record so a typo in one place does not hide a pair: the first four letters, the
    letters of the first word in sorted order (catches swapped letters) and the run-together name, which also meets
    the domain stem."""
    keys = set()
    if r.domain:
        keys.add(f"d:{r.domain}")
        keys.add(f"s:{r.domain.split('.')[0].replace('-', '')[:6]}")
    for n in r.names:
        k = name_key(n, translit)
        if k:
            t = k.split()[0]
            keys.add(f"n:{t[:4]}")
            keys.add(f"a:{''.join(sorted(t))}")
            keys.add(f"s:{k.replace(' ', '')[:6]}")
    return keys


def name_similarity(a: SourceRecord, b: SourceRecord, translit: bool = True) -> float:
    best = 0.0
    for x in a.names:
        for y in b.names:
            kx, ky = name_key(x, translit), name_key(y, translit)
            if kx and ky:
                cx, cy = compact_key(x, translit), compact_key(y, translit)
                best = max(best, fuzz.token_sort_ratio(kx, ky) / 100, fuzz.ratio(cx, cy) / 100)
    return best


def score(a: SourceRecord, b: SourceRecord, d: dict[str, Any], w: dict[str, float]) -> tuple[float, str]:
    translit = d["er_transliterate"]
    if d["er_domain_identifier"] and a.domain and b.domain and a.domain == b.domain:
        return 1.0, "same domain"
    if d["er_method"] == "fuzzy_name":
        return name_similarity(a, b, translit), "name"
    parts: list[tuple[float, float]] = []
    total = 0.0
    if a.names and b.names:
        parts.append((w["name"], name_similarity(a, b, translit)))
    if a.domain and b.domain:
        parts.append((w["domain"], 0.0))
    if a.city and b.city:
        parts.append((w["city"], 1.0 if transliterate(a.city) == transliterate(b.city) else 0.0))
    if a.country and b.country:
        parts.append((w["country"], 1.0 if a.country == b.country else 0.0))
    if a.founded and b.founded:
        parts.append((w["founded"], 1.0 if a.founded == b.founded else 0.0))
    if not parts:
        return 0.0, "nothing to compare"
    total = sum(x for x, _ in parts) if d["er_renormalise"] else sum(w.values())
    s = sum(x * v for x, v in parts) / total
    return s, "weighted " + ",".join(f"{v:.2f}" for _, v in parts)


def _bridge(records: list[SourceRecord], uf: _UF, res: Resolution, translit: bool, rc: dict[str, Any]) -> None:
    """A job-board domain with nothing else to compare meets a register entry with no domain. The domain stem
    'endorxelmaterials' proposes 'Endorxel Materials GmbH'; it decides only when the proposal is unique both ways,
    otherwise a person looks."""
    clusters: dict[str, list[SourceRecord]] = defaultdict(list)
    for r in records:
        clusters[uf.find(r.id)].append(r)
    lonely_domains: dict[str, list[SourceRecord]] = defaultdict(list)
    nameless_rooms: dict[str, list[str]] = defaultdict(list)
    for root, rs in clusters.items():
        if all(not r.names for r in rs) and len({r.domain for r in rs}) == 1:
            stem = re.sub(r"[-\d]+$", "", rs[0].domain.split(".")[0])
            lonely_domains[stem].append(rs[0])
        elif not any(r.domain for r in rs):
            for r in rs:
                for n in r.names:
                    nameless_rooms[compact_key(n, translit)].append(root)
    for stem, doms in lonely_domains.items():
        roots = sorted(set(nameless_rooms.get(stem, [])))
        if not roots:
            continue
        rep = clusters[roots[0]][0]
        if len(doms) == 1 and len(roots) == 1:
            uf.union(rep.id, doms[0].id)
            res.merged.append(Pair(rep.id, doms[0].id, float(rc["bridge_score"]), "unique name-domain bridge"))
        else:
            for dom in doms:
                for root in roots:
                    res.review.append(Pair(clusters[root][0].id, dom.id, float(rc["review_low"]),
                                           "name-domain bridge, not unique"))


def entity_id(record_ids: list[str]) -> str:
    return "E" + hashlib.sha1(min(record_ids).encode(), usedforsecurity=False).hexdigest()[:10]


def resolve(records: list[SourceRecord], d: dict[str, Any], cfg: dict[str, Any]) -> Resolution:
    ids = [r.id for r in records]
    uf = _UF(ids, {r.id: r.identifier for r in records})
    res = Resolution({}, {})
    if d["er_method"] == "exact":
        index: dict[str, list[str]] = defaultdict(list)
        for r in records:
            for n in r.names[:1]:
                index["n:" + n.lower().strip()].append(r.id)
            if r.domain and not r.names:
                index["d:" + r.domain].append(r.id)
        # the status quo joins job posts to vendor rows on the raw domain string
        for r in records:
            if r.domain and r.names and r.feed == "vendor_profiles":
                index["d:" + r.domain].append(r.id)
        for group in index.values():
            for x in group[1:]:
                if uf.union(group[0], x):
                    res.merged.append(Pair(group[0], x, 1.0, "exact"))
    else:
        rc = cfg["resolution"]
        w = {"name": rc["name_weight"], "domain": rc["domain_weight"], "city": rc["city_weight"],
             "country": rc["country_weight"], "founded": rc["founded_weight"]}
        hi, lo = float(rc["auto_merge"]), float(rc["review_low"])
        blocks: dict[str, list[SourceRecord]] = defaultdict(list)
        for r in records:
            for k in _keys(r, d["er_transliterate"]):
                blocks[k].append(r)
        seen: set[tuple[str, str]] = set()
        scored: list[Pair] = []
        for members in blocks.values():
            if len(members) > 400:
                continue
            for a, b in combinations(members, 2):
                key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                if key in seen or (a.identifier and b.identifier and a.identifier != b.identifier):
                    continue
                seen.add(key)
                s, why = score(a, b, d, w)
                if s >= lo:
                    scored.append(Pair(key[0], key[1], s, why))
        for p in sorted(scored, key=lambda x: -x.score):
            if p.score >= hi:
                (res.merged if uf.union(p.a, p.b) else res.refused).append(p)
            else:
                res.review.append(p)
        _bridge(records, uf, res, d["er_transliterate"], rc)
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[uf.find(i)].append(i)
    for group in groups.values():
        e = entity_id(group)
        res.members[e] = sorted(group)
        for m in group:
            res.entity_of[m] = e
    # a doubtful pair already inside one entity is not a question any more
    res.review = [p for p in res.review if res.entity_of[p.a] != res.entity_of[p.b]]
    return res


def apply_decisions(res: Resolution, records: list[SourceRecord], same: set[tuple[str, str]]) -> Resolution:
    """Re-cluster with the pairs a person confirmed in the review queue."""
    ids = [r.id for r in records]
    uf = _UF(ids, {r.id: r.identifier for r in records})
    for p in res.merged:
        uf.union(p.a, p.b)
    for a, b in same:
        uf.union(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[uf.find(i)].append(i)
    out = Resolution({}, {}, [], res.merged, res.refused)
    for members in groups.values():
        e = entity_id(members)
        out.members[e] = sorted(members)
        for m in members:
            out.entity_of[m] = e
    out.review = [p for p in res.review if out.entity_of[p.a] != out.entity_of[p.b] and (p.a, p.b) not in same]
    return out
