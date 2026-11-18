"""A simulated company-data market with hidden truth.

The world knows which records are the same company, what each news article really says about a relationship, when a
round really closed and when a company was really acquired. It delivers what vendors, registers, scrapers and job
boards would deliver, with their flaws: name variants, transliterations, typos, duplicate deliveries, announcement
lags, German register text, outages, schema drift and late backfills. The product never imports this module.

Every random draw is a hash of (seed, event) so all designs meet the same luck.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SYL = ["no", "va", "kra", "ft", "lum", "en", "ber", "gen", "tek", "sol", "ar", "is", "mo", "ra", "zen", "dor", "fi",
       "lix", "qua", "ntu", "vel", "ox", "ion", "ter", "ka", "li", "sto", "ne", "pi", "xel"]
GERMAN_WORDS = ["Grünfeld", "Müller", "Schönwerk", "Größe", "Bärwald", "Fröhlich", "Kühn", "Weißhaus", "Möwe",
                "Sonnenhöhe", "Blümel", "Brückner"]
SECTOR_WORDS = {"robotics": "Robotics", "energy": "Energy", "logistics": "Logistics", "ai": "AI", "health": "Health",
                "fintech": "Pay", "mobility": "Mobility", "materials": "Materials", "security": "Security",
                "climate": "Climate"}
COUNTRIES = [("DE", ["Berlin", "München", "Hamburg", "Köln", "Stuttgart", "Düsseldorf"], "GmbH"),
             ("AT", ["Wien", "Graz"], "GmbH"), ("CH", ["Zürich", "Basel"], "AG"),
             ("FR", ["Paris", "Lyon"], "SAS"), ("NL", ["Amsterdam", "Delft"], "B.V."),
             ("GB", ["London", "Manchester"], "Ltd"), ("US", ["Boston", "San Francisco"], "Inc."),
             ("SE", ["Stockholm"], "AB"), ("ES", ["Barcelona", "Madrid"], "S.L.")]
CORP_STEMS = ["Nordhaus", "Rheinwerk", "Südstahl", "Elbtal", "Alpenland", "Hanseatic", "Mainau", "Westfalen",
              "Isarwerke", "Bodensee", "Spreetal", "Neckar", "Moselle", "Taunus", "Harzer"]
CORP_KINDS = ["Industries", "Automotive", "Chemie", "Energie", "Versicherung", "Logistik", "Pharma", "Maschinenbau",
              "Retail", "Telekom"]
LABELS = ["mention", "partnership", "poc", "implementation", "investment", "acquisition"]


def _h(*key: Any) -> float:
    d = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return int.from_bytes(d, "big") / 2**64


def _pick(seq: list[Any] | tuple[Any, ...], *key: Any) -> Any:
    return seq[int(_h(*key) * len(seq)) % len(seq)]


def _int(lo: int, hi: int, *key: Any) -> int:
    return lo + int(_h(*key) * (hi - lo + 1))


def load(name: str = "world") -> dict[str, Any]:
    with open(ROOT / "config" / f"{name}.toml", "rb") as f:
        return tomllib.load(f)


@dataclass
class Company:
    id: str
    kind: str                      # startup | corporate
    name: str
    legal: str
    country: str
    city: str
    domain: str
    founded: int
    sector: str
    headcount: list[int]           # per week
    status: str = "active"
    acquired_by: str | None = None
    acquired_on: date | None = None
    shut_on: date | None = None
    rounds: list[tuple[date, int, str]] = field(default_factory=list)
    headcount_change: tuple[int, float] | None = None   # (week, factor)
    old_name: str | None = None


@dataclass
class Relationship:
    id: str
    corporate: str
    startup: str
    kind: str
    on: date


@dataclass
class TrueEvent:
    company: str
    kind: str                      # funding | acquisition | shutdown | headcount
    on: date


class World:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.seed = cfg["seed"]
        self.start = date.fromisoformat(cfg["start"])
        self.days = int(cfg["days"])
        self.weeks = self.days // 7
        self.companies: dict[str, Company] = {}
        self._make_companies()
        self.relationships: list[Relationship] = self._make_relationships()
        self.events: list[TrueEvent] = self._make_events()
        # truth maps filled while rendering deliveries
        self.source_truth: dict[tuple[str, str], str] = {}      # (feed, source key) -> company id
        self.article_truth: dict[str, dict[str, Any]] = {}       # url -> {corporate, startup, label, ambiguous}
        self._deliveries: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self._render()

    # ------------------------------------------------------------------ truth
    def day(self, i: int) -> date:
        return self.start + timedelta(days=i)

    def _make_companies(self) -> None:
        s = self.seed
        n = self.cfg["names"]
        generic_pool: list[str] = []
        for i in range(self.cfg["startups"]):
            cid = f"S{i:05d}"
            k = (s, cid)
            country, cities, legal = _pick(COUNTRIES, *k, "country")
            if _h(*k, "dach") < self.cfg["register"]["dach_share"]:
                country, cities, legal = _pick(COUNTRIES[:3], *k, "dachc")
            sector = _pick(list(SECTOR_WORDS), *k, "sector")
            if country in ("DE", "AT", "CH") and _h(*k, "germanword") < 0.35:
                stem = _pick(GERMAN_WORDS, *k, "gw")
            else:
                stem = "".join(_pick(SYL, *k, "syl", j) for j in range(_int(2, 3, *k, "nsyl"))).capitalize()
            name = f"{stem} {SECTOR_WORDS[sector]}"
            if generic_pool and _h(*k, "generic") < n["shared_generic_name"]:
                name = _pick(generic_pool, *k, "gpick")           # a different company with the same name
            generic_pool.append(name)
            city = _pick(cities, *k, "city")
            # The register refuses a second firm with the same name at the same seat (§30 HGB); we apply that
            # everywhere, so two companies can share a name only in different cities.
            taken = {(c.name, c.city) for c in self.companies.values()}
            j = 0
            while (name, city) in taken:
                j += 1
                city = _pick([x for _, cs, _ in COUNTRIES for x in cs], *k, "city2", j)
                if j > 5:
                    name, city = f"{name} {cid[-3:]}", _pick(cities, *k, "city")
                    break
            domain = self._domain(name, cid)
            weeks = self.days // 7
            base = _int(4, 260, *k, "hc")
            hc = [base] * weeks
            c = Company(cid, "startup", name, legal, country, city, domain,
                        _int(2008, 2025, *k, "founded"), sector, hc)
            if _h(*k, "rebrand") < n["rebrand"]:
                c.old_name = name
                c.name = f"{_pick(SYL, *k, 'rb1').capitalize()}{_pick(SYL, *k, 'rb2')} {SECTOR_WORDS[sector]}"
            self.companies[cid] = c
        for i in range(self.cfg["corporates"]):
            cid = f"C{i:03d}"
            k = (s, cid)
            name = f"{_pick(CORP_STEMS, *k, 'stem')} {_pick(CORP_KINDS, *k, 'kind')}"
            name = name if not any(c.name == name for c in self.companies.values()) else f"{name} {i}"
            country, cities, legal = _pick(COUNTRIES[:3], *k, "country")
            self.companies[cid] = Company(cid, "corporate", name, "AG" if country != "AT" else "AG", country,
                                          _pick(cities, *k, "city"), self._domain(name, cid),
                                          _int(1880, 1990, *k, "founded"), "corporate",
                                          [_int(2000, 90000, *k, "hc")] * (self.days // 7))

    def _domain(self, name: str, cid: str) -> str:
        """Domains are unique, as on the internet."""
        base = name.lower().replace(" ", "")
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            base = base.replace(a, b)
        tld = _pick(["com", "de", "io", "ai", "eu"], self.seed, cid, "tld")
        d = f"{base}{cid[-2:] if _h(self.seed, cid, 'dsuffix') < 0.5 else ''}.{tld}"
        taken = {c.domain for c in self.companies.values()}
        return d if d not in taken else f"{base}-{cid.lower()}.{tld}"

    def _make_relationships(self) -> list[Relationship]:
        out = []
        startups = [c for c in self.companies.values() if c.kind == "startup"]
        for corp in [c for c in self.companies.values() if c.kind == "corporate"]:
            n = _int(8, 45, self.seed, corp.id, "nrel")
            for j in range(n):
                st = _pick(startups, self.seed, corp.id, "st", j)
                kind = _pick(["mention", "partnership", "poc", "poc", "implementation", "investment", "partnership",
                              "mention"], self.seed, corp.id, "kind", j)
                on = self.day(_int(-120, self.days - 1, self.seed, corp.id, "on", j))
                out.append(Relationship(f"R{corp.id}{j:03d}", corp.id, st.id, kind, on))
        return out

    def _make_events(self) -> list[TrueEvent]:
        ev = []
        e = self.cfg["events"]
        for c in self.companies.values():
            if c.kind != "startup":
                continue
            k = (self.seed, c.id)
            if _h(*k, "fund") < e["funding_rate"]:
                on = self.day(_int(0, self.days - 20, *k, "fundon"))
                c.rounds.append((on, _int(1, 40, *k, "amt") * 500_000, _pick(["Seed", "Series A", "Series B"], *k,
                                                                                  "round")))
                ev.append(TrueEvent(c.id, "funding", on))
            if c.acquired_on is None and _h(*k, "acq") < e["acquisition_rate"]:
                on = self.day(_int(5, self.days - 25, *k, "acqon"))
                corp = _pick([x for x in self.companies.values() if x.kind == "corporate"], *k, "acqby")
                c.status, c.acquired_by, c.acquired_on = "acquired", corp.id, on
                self.relationships.append(Relationship(f"RA{c.id}", corp.id, c.id, "acquisition", on))
                ev.append(TrueEvent(c.id, "acquisition", on))
            elif c.acquired_on is None and _h(*k, "shut") < e["shutdown_rate"]:
                on = self.day(_int(5, self.days - 25, *k, "shuton"))
                c.status, c.shut_on = "shut_down", on
                ev.append(TrueEvent(c.id, "shutdown", on))
            if _h(*k, "hcchange") < 0.08 and c.status == "active":
                wk = _int(4, self.weeks - 5, *k, "hcweek")
                factor = _pick([0.6, 0.7, 1.4, 1.6, 1.9], *k, "hcf")
                c.headcount = [h if w < wk else max(2, int(h * factor)) for w, h in enumerate(c.headcount)]
                c.headcount_change = (wk, factor)
                ev.append(TrueEvent(c.id, "headcount", self.start + timedelta(days=7 * wk)))
        return ev

    # ------------------------------------------------------------------ rendering what sources deliver
    def _variant(self, c: Company, source: str, salt: Any = 0) -> str:
        n = self.cfg["names"]
        k = (self.seed, c.id, source, salt)
        name = c.name
        if c.old_name and source == "vendor_profiles" and _h(*k, "stale") < 0.7:
            name = c.old_name                                  # the vendor still has the old name
        if source == "register_notices":
            name = f"{name} {c.legal}"                          # the register always has the legal form
        elif _h(*k, "legal") < n["legal_suffix"]:
            name = f"{name} {c.legal}"
        if source != "register_notices" and _h(*k, "uml") < n["umlaut_transliteration"]:
            for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue")):
                name = name.replace(a, b)
        if _h(*k, "typo") < n["typo"] and len(name) > 6:
            i = _int(1, len(name) - 3, *k, "typopos")
            name = name[:i] + name[i + 1] + name[i] + name[i + 2:]
        if source == "news_mentions" and c.kind == "startup" and _h(*k, "short") < 0.4:
            name = name.split(" ")[0]                           # press often drops the sector word
        return name

    def _domain_variant(self, c: Company, source: str) -> str:
        k = (self.seed, c.id, source)
        d = c.domain
        if _h(*k, "www") < self.cfg["names"]["www_or_path_domain"]:
            d = _pick([f"https://www.{d}/", f"www.{d}", f"http://{d}/en/about", f"{d.upper()}"], *k, "wv")
        return d

    def _render(self) -> None:
        for d in range(self.days):
            for feed in ("vendor_profiles", "register_notices", "news_mentions"):
                self._deliveries[(feed, d)] = []
        for w in range(self.weeks):
            self._deliveries[("job_posts", w * 7)] = []
        self._render_vendor()
        self._render_register()
        self._render_news()
        self._render_jobs()

    def _vendor_row(self, c: Company, vid: str, d: int) -> dict[str, Any]:
        k = (self.seed, vid, d)
        week = min(d // 7, self.weeks - 1)
        noise = 1 + (_h(*k, "hcn") - 0.5) * 2 * self.cfg["vendor"]["headcount_noise"]
        rounds = []
        lo, hi = self.cfg["vendor"]["funding_announce_lag_days"]
        for on, amount, rnd in c.rounds:
            seen = on + timedelta(days=_int(lo, hi, self.seed, c.id, "lag", on))
            if seen <= self.day(d):
                stated = seen if _h(self.seed, c.id, "datebug", on) < self.cfg["vendor"]["date_is_entry_date"] else on
                rounds.append({"round": rnd, "amount_eur": amount, "announced_on": stated.isoformat()})
        status = c.status if ((c.acquired_on and self.day(d) >= c.acquired_on + timedelta(days=30))
                              or (c.shut_on and self.day(d) >= c.shut_on + timedelta(days=30))) else "active"
        return {"vendor_id": vid, "name": self._variant(c, "vendor_profiles", vid),
                "domain": self._domain_variant(c, "vendor_profiles"), "country": c.country, "city": c.city,
                "founded_year": c.founded if _h(*k, "foundednull") > 0.05 else None,
                "headcount": max(1, int(c.headcount[week] * noise)), "status": status, "funding_rounds": rounds,
                "founder_email": f"founder@{c.domain}" if c.kind == "startup" else None}

    def _render_vendor(self) -> None:
        v = self.cfg["vendor"]
        covered = [c for c in self.companies.values() if _h(self.seed, c.id, "vcov") < v["coverage"]]
        for c in covered:
            vids = [f"v-{_int(100000, 999999, self.seed, c.id, 'vid')}"]
            if _h(self.seed, c.id, "vdup") < 0.04:                       # the vendor itself has a duplicate
                vids.append(f"v-{_int(100000, 999999, self.seed, c.id, 'vid2')}")
            for vid in vids:
                self.source_truth[("vendor_profiles", vid)] = c.id
                self._deliveries[("vendor_profiles", 0)].append(self._vendor_row(c, vid, 0))
                # an update whenever something the vendor knows changed
                change_days = set()
                for on, _, _ in c.rounds:
                    lo, hi = v["funding_announce_lag_days"]
                    change_days.add((on - self.start).days + _int(lo, hi, self.seed, c.id, "lag", on))
                for on in (c.acquired_on, c.shut_on):
                    if on:
                        change_days.add((on - self.start).days + 30)
                if c.headcount_change:
                    change_days.add(c.headcount_change[0] * 7 + _int(7, 30, self.seed, c.id, "hclag"))
                for cd in sorted(x for x in change_days if 0 < x < self.days):
                    self._deliveries[("vendor_profiles", cd)].append(self._vendor_row(c, vid, cd))
                    if _h(self.seed, vid, cd, "dupdeliv") < v["duplicate_delivery"]:
                        self._deliveries[("vendor_profiles", cd)].append(self._vendor_row(c, vid, cd))
        # small daily churn: profiles touched without real change (realistic volume)
        for d in range(1, self.days):
            for i in range(_int(20, 45, self.seed, "churn", d)):
                c = _pick(covered, self.seed, "churnc", d, i)
                vid = f"v-{_int(100000, 999999, self.seed, c.id, 'vid')}"
                self._deliveries[("vendor_profiles", d)].append(self._vendor_row(c, vid, d))

    def _register_row(self, c: Company, kind: str, d: int, text: str) -> dict[str, Any]:
        nid = f"HR-{_int(1000000, 9999999, self.seed, c.id, kind, d)}"
        self.source_truth[("register_notices", nid)] = c.id
        court = {"DE": "Amtsgericht", "AT": "Landesgericht", "CH": "Handelsregisteramt"}[c.country]
        regno = f"HRB {_int(10000, 299999, self.seed, c.id, 'hrb')}"
        return {"notice_id": nid, "court": f"{court} {c.city}", "register_no": regno,
                "company_name": self._variant(c, "register_notices"), "seat": c.city, "country": c.country,
                "published_on": self.day(d).isoformat(), "kind": kind, "text": text}

    def _render_register(self) -> None:
        r = self.cfg["register"]
        for c in self.companies.values():
            if c.country not in ("DE", "AT", "CH") or c.kind != "startup" or _h(self.seed, c.id, "rcov") > r[
                    "coverage_dach"]:
                continue
            nm = self._variant(c, "register_notices")
            self._deliveries[("register_notices", 0)].append(self._register_row(
                c, "eintragung", 0, f"Neueintragung. {nm}, {c.city}. Gegenstand des Unternehmens: "
                                     f"{c.sector.capitalize()}. Gründungsjahr {c.founded}."))
            if c.acquired_on:
                d = (c.acquired_on - self.start).days + _int(10, 35, self.seed, c.id, "reglag")
                buyer = self.companies[c.acquired_by or ""]
                if d < self.days:
                    self._deliveries[("register_notices", d)].append(self._register_row(
                        c, "verschmelzung", d, f"Verschmelzung. Die Gesellschaft {nm} ist auf Grund des "
                                               f"Verschmelzungsvertrages vom {c.acquired_on:%d.%m.%Y} mit der "
                                               f"{buyer.name} {buyer.legal} verschmolzen."))
            if c.shut_on:
                d = (c.shut_on - self.start).days + _int(7, 28, self.seed, c.id, "reglag")
                kind = _pick(["liquidation", "insolvenz"], self.seed, c.id, "shutkind")
                text = (f"Auflösung. Die Gesellschaft {nm} ist durch Beschluss der Gesellschafterversammlung vom "
                        f"{c.shut_on:%d.%m.%Y} aufgelöst. Liquidator: bestellt." if kind == "liquidation" else
                        f"Insolvenzverfahren. Über das Vermögen der {nm} wurde am {c.shut_on:%d.%m.%Y} das "
                        f"Insolvenzverfahren eröffnet.")
                if d < self.days:
                    self._deliveries[("register_notices", d)].append(self._register_row(c, kind, d, text))
            if c.old_name:
                d = _int(1, self.days - 1, self.seed, c.id, "rbday")
                self._deliveries[("register_notices", d)].append(self._register_row(
                    c, "firmenaenderung", d, f"Änderung der Firma. Bisher: {c.old_name} {c.legal}. Neu: {nm}."))

    def _render_news(self) -> None:
        nw = self.cfg["news"]
        n_id = 0
        for r in self.relationships:
            lo, hi = nw["mentions_per_relationship"]
            for j in range(_int(lo, hi, self.seed, r.id, "nm")):
                d = (r.on - self.start).days + _int(0, 3, self.seed, r.id, "nlag", j)
                if not 0 <= d < self.days:
                    continue
                corp, st = self.companies[r.corporate], self.companies[r.startup]
                amb = r.kind not in ("acquisition", "mention") and _h(self.seed, r.id, "amb", j) < nw["ambiguous_share"]
                novel = _h(self.seed, r.id, "novel", j) < nw.get("unseen_phrasing_share", 0.0)
                de = _h(self.seed, r.id, "de", j) < nw["german_share"]
                text = _article(r.kind, self._variant(corp, "news_mentions", (r.id, j)),
                                self._variant(st, "news_mentions", (r.id, j)), amb, de, (self.seed, r.id, j), novel)
                url = f"https://news.example/{r.on.year}/{n_id:06d}"
                n_id += 1
                self.article_truth[url] = {"corporate": corp.id, "startup": st.id, "label": r.kind,
                                           "ambiguous": amb, "german": de, "relationship": r.id}
                self._deliveries[("news_mentions", d)].append(
                    {"url": url, "published_on": self.day(d).isoformat(), "language": "de" if de else "en",
                     "title": text.split(". ")[0][:90], "text": text,
                     "startup_domain": self._domain_variant(st, "news_mentions") if _h(self.seed, url,
                                                                                        "dom") < 0.5 else None})
        startups = [c for c in self.companies.values() if c.kind == "startup"]
        corps = [c for c in self.companies.values() if c.kind == "corporate"]
        for d in range(self.days):
            for i in range(int(_int(4, 12, self.seed, "noise", d) * nw["noise_mentions"] / 0.2)):
                st, corp = _pick(startups, self.seed, "nst", d, i), _pick(corps, self.seed, "ncp", d, i)
                url = f"https://news.example/x/{d:03d}{i:03d}"
                corp_name = self._variant(corp, "news_mentions", url)
                text = (f"Among the exhibitors at this year's trade fair were {corp_name} "
                        f"and {self._variant(st, 'news_mentions', url)}, alongside dozens of others.")
                self.article_truth[url] = {"corporate": corp.id, "startup": st.id, "label": "none",
                                           "ambiguous": False, "german": False, "relationship": None}
                self._deliveries[("news_mentions", d)].append(
                    {"url": url, "published_on": self.day(d).isoformat(), "language": "en", "title": text[:90],
                     "text": text, "startup_domain": None})

    def _render_jobs(self) -> None:
        jn = self.cfg["jobs"]["weekly_noise"]
        for c in self.companies.values():
            if c.kind != "startup":
                continue
            for w in range(self.weeks):
                if c.shut_on and self.start + timedelta(days=7 * w) > c.shut_on:
                    continue
                k = (self.seed, c.id, "jobs", w)
                lam = max(0.0, c.headcount[w] * 0.06 * (1 + (_h(*k) - 0.5) * 2 * jn))
                key = f"{w}:{c.domain}"
                self.source_truth[("job_posts", key)] = c.id
                self._deliveries[("job_posts", w * 7)].append(
                    {"post_week_domain": key, "week_start": (self.start + timedelta(days=7 * w)).isoformat(),
                     "domain": c.domain, "open_posts": int(round(lam))})

    def customers(self) -> list[dict[str, Any]]:
        """GlassDollar's own CRM: the corporates it serves. Not hidden truth, the product owns this list."""
        out = []
        for c in self.companies.values():
            if c.kind == "corporate":
                self.source_truth[("crm", f"crm-{c.id}")] = c.id
                out.append({"crm_id": f"crm-{c.id}", "name": f"{c.name} {c.legal}", "domain": c.domain,
                            "country": c.country, "city": c.city})
        return out

    # ------------------------------------------------------------------ what the pipeline can fetch
    def _outage(self, feed: str, d: int) -> str | None:
        for f, start, length, kind in self.cfg["outages"]["plan"]:
            if f == feed and start <= d < start + length:
                return str(kind)
        return None

    def fetch(self, feed: str, d: int) -> list[dict[str, Any]] | None:
        """The file a feed delivers for day d, or None if nothing arrived (outage or not a delivery day)."""
        rows = self._deliveries.get((feed, d))
        if rows is None:
            return None
        kind = self._outage(feed, d)
        if kind == "stop":
            return None
        rows = [dict(r) for r in rows]
        if kind == "volume":
            rows = [r for i, r in enumerate(rows) if _h(self.seed, feed, d, i, "vol") < 0.2]
        if kind == "drift":
            renames = {"vendor_profiles": ("headcount", "employee_count"),
                       "register_notices": ("text", "bekanntmachung"),
                       "news_mentions": ("text", "body"), "job_posts": ("open_posts", "openings")}
            a, b = renames[feed]
            for r in rows:
                r[b] = r.pop(a, None)
        return rows

    def backfill(self, feed: str, d: int, today: int) -> list[dict[str, Any]] | None:
        """After an outage is over the provider can redeliver a missed day in full, correctly shaped."""
        rows = self._deliveries.get((feed, d))
        if rows is None:
            return None
        for f, start, length, _ in self.cfg["outages"]["plan"]:
            if f == feed and start <= d < start + length and today < start + length:
                return None                                   # still down: nothing to redeliver yet
        return [dict(r) for r in rows]

    def outages(self) -> list[tuple[str, int, int, str]]:
        return [tuple(x) for x in self.cfg["outages"]["plan"]]  # type: ignore[misc]

    # ------------------------------------------------------------------ simulated model and people
    def llm_label(self, url: str, tier: str) -> tuple[str, float, int]:
        """A simulated LLM classifying an article: (label, self-reported confidence, tokens)."""
        t = self.article_truth[url]
        m = self.cfg["models"]
        amb = t["ambiguous"]
        acc = m[f"{tier}_accuracy_{'ambiguous' if amb else 'clear'}"]
        k = (self.seed, url, tier)
        lo, hi = m["tokens_per_snippet"]
        tokens = _int(lo, hi, *k, "tok")
        if _h(*k, "ok") < acc:
            return t["label"], 0.75 + 0.24 * _h(*k, "conf"), tokens
        near = {"mention": "partnership", "partnership": "poc", "poc": "implementation", "implementation": "poc",
                "investment": "partnership", "acquisition": "investment", "none": "mention"}
        wrong = near[t["label"]] if _h(*k, "near") < 0.7 else _pick([lab for lab in LABELS if lab != t["label"]], *k,
                                                                     "w")
        return wrong, 0.40 + 0.50 * _h(*k, "wconf"), tokens

    def person_label(self, url: str) -> str:
        return str(self.article_truth[url]["label"])

    def same_company(self, a: tuple[str, str], b: tuple[str, str]) -> bool:
        return self.source_truth.get(a) == self.source_truth.get(b)


NOVEL = {   # phrasings that only the held-out world uses (unseen_phrasing_share): no rule was written against them
    "mention": ["{st} was one of the startups on stage when {corp} hosted its supplier summit."],
    "partnership": ["{corp} teams up with {st}.", "{st} and {corp} join forces on industrial software."],
    "poc": ["{corp} trials {st}'s sensors on a single production line.",
            "{corp} und {st} testen gemeinsam einen neuen Ansatz in der Fertigung."],
    "implementation": ["{st}'s platform is now live in every {corp} plant."],
    "investment": ["{corp} takes a minority stake in {st}.",
                   "{corp} hält künftig eine Minderheitsbeteiligung an {st}."],
    "acquisition": ["{corp} snaps up {st}.", "{corp} erwirbt sämtliche Anteile an {st}."],
}


def _article(kind: str, corp: str, st: str, ambiguous: bool, german: bool, k: tuple[Any, ...],
             novel: bool = False) -> str:
    """The text a press article would carry. Clear wording names the relationship; ambiguous wording does not."""
    if novel and not ambiguous:
        return _pick(NOVEL[kind], *k, "novel").format(corp=corp, st=st) + " Further details were not disclosed."
    if german:
        clear = {
            "mention": [f"Auf dem Innovationstag von {corp} stellte {st} seine Lösung vor."],
            "partnership": [f"{corp} und {st} geben eine strategische Partnerschaft bekannt.",
                            f"{corp} startet eine Kooperation mit {st}."],
            "poc": [f"{corp} testet die Technologie von {st} in einem Pilotprojekt.",
                    f"{st} und {corp} starten einen Proof of Concept im Werk."],
            "implementation": [f"{corp} setzt die Software von {st} nun an allen Standorten ein.",
                               f"Nach erfolgreichem Test führt {corp} die Lösung von {st} flächendeckend ein."],
            "investment": [f"{corp} beteiligt sich an {st} im Rahmen einer Finanzierungsrunde.",
                           f"Der Corporate-VC von {corp} investiert in {st}."],
            "acquisition": [f"{corp} übernimmt das Start-up {st}.", f"{st} wird von {corp} übernommen."],
        }
        vague = [f"{corp} und {st} arbeiten künftig enger zusammen.",
                 f"{st} meldet einen wichtigen Schritt mit {corp}.",
                 f"{corp} setzt bei der Digitalisierung auf {st}."]
    else:
        clear = {
            "mention": [f"{st} presented its product at the {corp} innovation day.",
                        f"Speakers from {corp} and {st} joined a panel on the future of industry."],
            "partnership": [f"{corp} and {st} announce a strategic partnership.",
                            f"{st} partners with {corp} to bring its platform to more customers."],
            "poc": [f"{corp} is piloting {st}'s technology at one of its plants.",
                    f"{st} and {corp} kick off a proof of concept.",
                    f"{corp} runs a PoC with {st} to test the approach."],
            "implementation": [f"{corp} has rolled out {st}'s software across all sites.",
                               f"After a successful pilot, {corp} deploys {st} company-wide."],
            "investment": [f"{corp} Ventures led the latest funding round of {st}.",
                           f"{corp} invested in {st} as part of its Series A."],
            "acquisition": [f"{corp} acquires {st}.", f"{st} has been acquired by {corp}."],
        }
        vague = [f"{corp} and {st} are working together on the next generation of products.",
                 f"{st} announced a milestone with {corp} this week.",
                 f"{corp} is betting on {st} for its digital transformation.",
                 f"{corp} and {st} deepen their relationship."]
    if ambiguous and kind != "mention":
        return _pick(vague, *k, "vague") + " Further details were not disclosed."
    return _pick(clear[kind], *k, "clear") + " Further details were not disclosed."
