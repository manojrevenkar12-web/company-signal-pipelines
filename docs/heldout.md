# Held-out protocol

1. The code is final and committed.
2. Run `make heldout`. It runs `evals.run --heldout`, writes `reports/heldout.json` and
   `reports/heldout.lock` (commit and code fingerprint), and refuses any second run.
3. Run `make report` and commit the report, the lock and the README together.
4. A bad number stays in the README. A fix needs a new held-out world declared here before it is run.

| world | seed | declared | run |
|---|---|---|---|
| heldout | 977 | with the first commit | see `reports/heldout.lock` |
