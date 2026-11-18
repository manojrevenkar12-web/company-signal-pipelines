"""Keyword rules for relationship types, English and German. A rule fires only on wording that names the
relationship; vague wording ("working together", "arbeiten zusammen") is left to a model.

The order is the precedence when several fire: "after a successful pilot, X deploys Y" is an implementation.
"""

from __future__ import annotations

import re

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("none", re.compile(r"\b(exhibitors?|trade fair|alongside dozens)\b", re.I)),
    ("acquisition", re.compile(r"\b(acquires?|acquired by|übernimmt|übernommen|takeover)\b", re.I)),
    ("investment", re.compile(r"\b(invest(s|ed|ment)?|ventures led|funding round|beteiligt sich|"
                              r"finanzierungsrunde|corporate-vc)\b", re.I)),
    ("implementation", re.compile(r"\b(rolled out|deploys?|company-wide|across all sites|flächendeckend|"
                                  r"an allen standorten)\b", re.I)),
    ("poc", re.compile(r"\b(pilot(ing)?|proof of concept|poc|pilotprojekt|testet)\b", re.I)),
    ("partnership", re.compile(r"\b(strategic partnership|partners with|partnerschaft|kooperation)\b", re.I)),
    ("mention", re.compile(r"\b(innovation day|panel|innovationstag|presented its product)\b", re.I)),
]


def rule_label(text: str) -> str | None:
    for label, pattern in RULES:
        if pattern.search(text):
            return label
    return None
