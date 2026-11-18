"""Relationship classification: rules first, a small model next, a large model for what the small one is unsure of,
a person for what the large one is unsure of. The model reads; code decides which answer is accepted."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from signals.classify.rules import rule_label


class Model(Protocol):
    name: str

    def label(self, article: dict[str, Any]) -> tuple[str, float, int]:
        """(label, self-reported confidence 0..1, tokens used)."""
        ...


@dataclass
class Decision:
    url: str
    label: str
    decided_by: str          # rule | cheap | expensive | review
    confidence: float
    cost_eur: float
    steps: str               # the path taken, e.g. "rule" or "cheap>expensive>review"


def classify(article: dict[str, Any], design: dict[str, Any], cfg: dict[str, Any], cheap: Model,
             expensive: Model) -> Decision:
    c = cfg["classification"]
    url = article["url"]
    text = article.get("text") or article.get("body") or ""
    mode = design["classification"]
    p_cheap = float(c["cheap_eur_per_1k_tokens"]) / 1000
    p_exp = float(c["expensive_eur_per_1k_tokens"]) / 1000
    if mode == "rules":
        lab = rule_label(text)
        return Decision(url, lab or "mention", "rule", float(c["rule_confidence"]) if lab else 0.0, 0.0,
                        "rule" if lab else "rule-default")
    if mode == "cheap":
        lab, conf, tok = cheap.label(article)
        return Decision(url, lab, "cheap", conf, tok * p_cheap, "cheap")
    if mode == "expensive":
        lab, conf, tok = expensive.label(article)
        return Decision(url, lab, "expensive", conf, tok * p_exp, "expensive")
    # cascade
    if design["cascade_rules"]:
        lab = rule_label(text)
        if lab:
            return Decision(url, lab, "rule", float(c["rule_confidence"]), 0.0, "rule")
    lab, conf, tok = cheap.label(article)
    cost = tok * p_cheap
    if conf >= float(c["cheap_accept"]):
        return Decision(url, lab, "cheap", conf, cost, "cheap")
    lab2, conf2, tok2 = expensive.label(article)
    cost += tok2 * p_exp
    if conf2 >= float(c["expensive_accept"]) or not design["review_queue"]:
        return Decision(url, lab2, "expensive", conf2, cost, "cheap>expensive")
    return Decision(url, lab2, "review", conf2, cost, "cheap>expensive>review")
