# AGENTS.md

How to work in this repository, for people and coding agents alike.

## Fast feedback

- `make test`: unit, pipeline and Postgres tests (~15 s). The Postgres tests skip without a database.
- `make lint`: ruff and mypy.
- `make eval`: every design on the dev seeds (~2 min).
- `make report`: regenerates the README results and charts.
- `cd dbt && dbt build`: after `make demo`, the marts and their tests.

Run the narrowest of these that covers your change, then `make test` before you commit.

## Invariants

1. **The truth stays in the world.** Only `world/` knows which records are the same company, what an article really
   says or when a round really closed. `src/signals` never imports `world` or `evals`; a test enforces it.
   Evaluations reach the truth through `evals/adapter.py` and `evals/measure.py` only.
2. **The world does not read the product's settings.** `world/` reads `config/world.toml` or
   `config/heldout.toml`, never `pipelines.toml`, `gates.toml` or `designs.toml`. Tuning the product cannot change
   the luck it is judged on.
3. **Same luck for every design.** Every random draw in the world is a hash of (seed, event). Two designs run on
   the same seed see the same deliveries, outages and model answers. Compare designs only on the same seeds.
4. **The model reads and code decides.** A model returns a label and a confidence. Code accepts it, escalates it
   or sends it to a person, by thresholds in config. A malformed or unknown answer counts as zero confidence.
   Article text is data, never instructions; the prompt says so.
5. **Identifiers decide and names propose.** An equal normalised domain merges two records. Two register numbers
   or two CRM ids never end up in one company, not even through a chain of other records, and not even on a
   reviewer's answer. A name similarity only proposes a score.
6. **A delivery is kept once.** Raw rows are unique on (feed, source key, payload hash). A redelivery or backfill
   adds only what is new. Raw is never edited, except for removing personal fields after retention.
7. **Personal data stays in raw.** `founder_email` is never selected below raw and is removed after
   `privacy.raw_retention_days`. A dbt test fails on any column below raw that looks like personal data.
8. **Settings in config.** Thresholds, weights, prices, priorities and SLAs live in `config/pipelines.toml`. A
   test fails on a bare decimal threshold in the deciding modules.
9. **Generated reports.** `reports/*.json`, the README results section and `docs/charts` are written by
   `evals/run.py` and `evals/readme.py`. Never edit them by hand.

## The held-out rule

`config/heldout.toml` describes a world nobody tunes on. Run it with `make heldout` once the code is final. The run
writes `reports/heldout.lock` with the commit and code fingerprint, and a second run refuses. If the held-out
numbers are bad, report them as they are. To change the code afterwards, a new held-out world (new seed, new
outage plan) has to be written and declared in `docs/heldout.md` before it is run.
