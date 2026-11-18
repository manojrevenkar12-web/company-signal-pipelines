# 1. An idempotent raw layer with quarantine and backfills

## Status
Accepted

## Context
Vendors redeliver files, send the same row twice in one file and backfill missed days. The scraper resends
unchanged pages. If you append everything, you double-count companies and pay twice for nothing. Downstream, you
cannot tell a real change from a repeat.

## Decision
Raw rows are unique on (feed, source key, payload hash), with `INSERT ... ON CONFLICT DO NOTHING`.

- Every delivery is a `raw.load_run` row, scheduled or backfill, loaded or quarantined.
- A delivery that breaks the feed's contract (missing or unexpected fields) is quarantined: it is kept aside and
  never read, and a missed day is recorded for it.
- When a feed delivers cleanly again, the ingestor asks for every missed day and loads what is new.

## Consequences
- A redelivery costs nothing downstream.
- A changed row is a new raw row, so history is kept.
- The status quo design appends: on dev it keeps about 170 duplicate rows per run and loses the drifted register
  notices.
- The volume monitor alerts only on drops, because spikes are absorbed by the key.
