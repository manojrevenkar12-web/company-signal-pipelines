# 6. A held-out world, run once

## Decision
- The development world (seeds 11, 12, 13) is where thresholds were set.
- The held-out world (seed 977) has:
  - more typos (8%) and rebrands (4%);
  - more shared names;
  - a third more vague wording;
  - 25% German articles;
  - 30% of clear wording in phrasings no rule was written for;
  - a vendor that misdates 15% of rounds;
  - a different outage plan: vendor drift, a five-day press stop, a thin register week, and a three-week job-board
    stop.
- It runs once behind `reports/heldout.lock`, on the final code, and its numbers are reported as they come.
