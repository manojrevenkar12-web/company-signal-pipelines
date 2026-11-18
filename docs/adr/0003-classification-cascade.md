# 3. Rules, then a small model, then a large model, then a person

## Context
GlassDollar has to label a large backlog of corporate–startup mentions, and a daily inflow on top of it. Sending
every article to a large model is accurate enough, but on dev it costs €4.51 per 1,000 articles, above the €4.00
budget. A small model alone is cheap but reaches only 90% precision.

## Decision
1. Keyword rules (English and German) fire only on wording that names the relationship. They cost nothing.
2. The small model answers next. Its label is accepted at confidence ≥ 0.85.
3. Otherwise the large model answers. Its label is accepted at confidence ≥ 0.70.
4. Below that, a person decides.

The model reads; code decides. A malformed or unknown answer counts as zero confidence and escalates.

## Consequences
On dev: 99.1% precision at €0.37 per 1,000 articles, with about 16 articles per run for a person.

- Without rules: €2.36 per 1,000.
- Without review: 98.6% precision.

The rules were written against the dev world's wording. The held-out world measures what happens when 30% of clear
wording is new.
