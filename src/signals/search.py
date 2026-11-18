"""Company search over golden names and every alias. The same idea runs in Postgres with pg_trgm (see
migrations/002 and the API); this version serves tests and the benchmark."""

from __future__ import annotations

from rapidfuzz import fuzz, process

from signals.normalize import name_key


class NameIndex:
    def __init__(self, names: dict[str, list[str]]):
        """entity id -> names (golden name first)."""
        self.keys: list[str] = []
        self.owner: list[str] = []
        for e, ns in names.items():
            for n in ns:
                k = name_key(n)
                if k:
                    self.keys.append(k)
                    self.owner.append(e)

    def search(self, query: str, k: int = 5, method: str = "fuzzy") -> list[str]:
        q = name_key(query) if method != "exact" else query.lower().strip()
        out: list[str] = []
        if method in ("exact", "normalised"):
            for key, e in zip(self.keys, self.owner):
                if key == q and e not in out:
                    out.append(e)
            return out[:k]
        for _, _, i in process.extract(q, self.keys, scorer=fuzz.WRatio, limit=k * 4):
            if self.owner[i] not in out:
                out.append(self.owner[i])
            if len(out) == k:
                break
        return out
