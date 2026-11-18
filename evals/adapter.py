"""The bridge between the world and the product. The product sees a Source, two Models, customers and a Reviewer;
only this module (and evals/) know they are backed by the simulation."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from world.generate import World


class SimModel:
    def __init__(self, world: World, tier: str):
        self.world, self.tier = world, tier
        self.name = f"simulated-{tier}"

    def label(self, article: dict[str, Any]) -> tuple[str, float, int]:
        return self.world.llm_label(article["url"], self.tier)


class Truth:
    """What the world knows about each source record id."""

    def __init__(self, world: World):
        self.world = world

    @cached_property
    def _register(self) -> dict[str, str]:
        out = {}
        for (feed, _), rows in self.world._deliveries.items():
            if feed != "register_notices":
                continue
            for r in rows:
                out[f"register_notices:{r['court']}|{r['register_no']}"] = self.world.source_truth[
                    ("register_notices", r["notice_id"])]
        return out

    @cached_property
    def _domains(self) -> dict[str, str]:
        return {c.domain: c.id for c in self.world.companies.values()}

    def company(self, record_id: str) -> str | None:
        feed, key = record_id.split(":", 1)
        if feed == "job_posts":
            return self._domains.get(key)
        if feed == "register_notices":
            return self._register.get(record_id)
        return self.world.source_truth.get((feed, key))


class SimReviewer:
    """A person working the review queues. Assumed right; the number of items they look at is reported."""

    def __init__(self, world: World):
        self.world = world
        self.truth = Truth(world)

    def same_company(self, a: str, b: str) -> bool:
        ta, tb = self.truth.company(a), self.truth.company(b)
        return ta is not None and ta == tb

    def relationship(self, url: str) -> str:
        return self.world.person_label(url)

    def which_company(self, url: str, candidates: dict[str, list[str]]) -> str | None:
        want = self.world.article_truth[url]["startup"]
        for entity, members in candidates.items():
            if any(self.truth.company(m) == want for m in members):
                return entity
        return None
