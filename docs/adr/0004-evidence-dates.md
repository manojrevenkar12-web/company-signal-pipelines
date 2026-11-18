# 4. A signal is dated by the earliest credible evidence

## Context
A funding round reaches the vendor 3 to 45 days after it is announced. A register merger notice is published up
to five weeks after the contract. If you date by load day, alerts are weeks late and sorted wrongly.

## Decision
Evidence carries two dates: what it states and when we first had it.

- A register notice states its contract or resolution date ("Verschmelzungsvertrag vom 03.06.2026").
- An article states its publication date.
- The vendor states the round's announcement date.

The event date is the earliest stated date. Evidence of one kind for one company within 21 days is one event.
Acquisitions and shutdowns happen once.

A company that had a jobs page every week and then vanished for two delivered weeks is a shutdown signal. This
does not apply to weeks when the jobs feed itself was down.

## Consequences
- Date error on dev is 1.7 days, against 19.4 days when dating by ingestion.
- The jobs-feed signal catches shutdowns of companies outside the register before the vendor's status flips,
  which takes about 30 days. Without it, 1.7 closed companies per run stay recommendable.
