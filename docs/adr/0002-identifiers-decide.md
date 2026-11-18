# 2. Identifiers decide, names propose

## Context
Names are what most sources share. They are also where the errors are:

- legal forms come and go ("Nova Robotics GmbH" against "Nova Robotics");
- umlauts are transliterated ("Grünfeld" against "Gruenfeld");
- there are typos and rebrands;
- different companies share a name in different cities.

## Decision
- An equal normalised domain merges two records, whatever the names say.
- A register number (court + HRB) and a CRM id are identifiers. Union–find refuses any merge that would put two
  of them in one company, including through a chain of other records and on a reviewer's "same".
- Everything else is a weighted score (name 0.50, domain 0.30, city 0.10, country 0.05, founded 0.05). The weights
  are renormalised over the fields both records have. Without that, a register notice, which has no domain, could
  never reach the merge threshold.
- Scores of 0.90 and above merge. Scores from 0.82 to 0.90 go to a person.
- A job-board domain whose stem matches exactly one register name, and only that one, is merged. Otherwise it goes
  to review.

## Consequences
On dev: precision 99.8%, recall 98.8% before review.

| Variant | Effect |
|---|---|
| Without renormalisation | recall 47.8% |
| Name-only fuzzy matching | precision 46.9% |
| Exact names (status quo) | precision 77.3%, recall 63.3% |
