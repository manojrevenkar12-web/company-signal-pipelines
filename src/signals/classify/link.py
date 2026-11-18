"""Which corporate and which startup an article is about. Identifiers decide (a startup domain in the article),
names propose (the gazetteer of resolved names); an article whose startup could be several companies is left
unlinked for a person rather than guessed."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from signals.normalize import domain_key, name_key


@dataclass
class Link:
    url: str
    corporate: str | None
    startup: str | None
    status: str                       # linked | ambiguous | unlinked
    candidates: list[str] = field(default_factory=list)


class Gazetteer:
    def __init__(self, corporates: dict[str, list[str]], startups: dict[str, list[str]],
                 domains: dict[str, str]):
        """corporates/startups: entity id -> names; domains: normalised domain -> entity id."""
        self.corp = sorted(((name_key(n), e) for e, ns in corporates.items() for n in ns if name_key(n)),
                           key=lambda x: -len(x[0]))
        self.corp_keys = [k for k, _ in self.corp]
        self.full: dict[str, set[str]] = defaultdict(set)
        self.first: dict[str, set[str]] = defaultdict(set)
        for e, ns in startups.items():
            for n in ns:
                k = name_key(n)
                if k:
                    self.full[k].add(e)
                    self.first[k.split()[0]].add(e)
        self.names = list(self.full)
        self.domains = domains

    def link(self, article: dict[str, Any]) -> Link:
        url = article["url"]
        text = article.get("text") or article.get("body") or ""
        norm = " " + name_key(re.sub(r"'s\b", "", text)) + " "
        corporate = None
        for k, e in self.corp:
            if f" {k} " in norm:
                corporate = e
                norm = norm.replace(f" {k} ", " | ", 1)
                break
        if corporate is None:
            # a typo in the corporate's name: the closest customer name inside the text, if close enough
            best = process.extractOne(norm, self.corp_keys, scorer=fuzz.partial_ratio, score_cutoff=90)
            if best:
                corporate = self.corp[best[2]][1]
                al = fuzz.partial_ratio_alignment(best[0], norm)
                if al is not None:
                    norm = norm[:al.dest_start] + " | " + norm[al.dest_end:]
        dom = domain_key(article.get("startup_domain"))
        if dom and dom in self.domains:
            return Link(url, corporate, self.domains[dom], "linked" if corporate else "unlinked")
        tokens = norm.split()
        hits: set[str] = set()
        for n in (3, 2):
            for i in range(len(tokens) - n + 1):
                hits |= self.full.get(" ".join(tokens[i:i + n]), set())
            if hits:
                break
        if not hits:
            singles = [self.first[t] for t in tokens if t in self.first]
            hits = set().union(*singles) if singles else set()
        if not hits:
            # a typo: compare word pairs of the text with every known name
            for i in range(len(tokens) - 1):
                gram = " ".join(tokens[i:i + 2])
                if "|" in gram or len(gram) < 6:
                    continue
                best = process.extractOne(gram, self.names, scorer=fuzz.ratio, score_cutoff=88)
                if best:
                    hits |= self.full[best[0]]
        if corporate is None or not hits:
            return Link(url, corporate, None, "unlinked", sorted(hits))
        if len(hits) > 1:
            return Link(url, corporate, None, "ambiguous", sorted(hits))
        return Link(url, corporate, next(iter(hits)), "linked")
