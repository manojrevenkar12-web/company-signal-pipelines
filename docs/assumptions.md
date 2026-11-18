# Assumptions

## Models (simulated; `config/world.toml [models]`)

| | clear wording | vague wording | confidence when right | confidence when wrong |
|---|---|---|---|---|
| small model | 93% | 70% | uniform 0.75–0.99 | uniform 0.40–0.90 |
| large model | 98.5% | 88% | uniform 0.75–0.99 | uniform 0.40–0.90 |

- Each answer uses 180–420 tokens.
- Prices are €0.0008 and €0.0150 per 1,000 tokens (`config/pipelines.toml [classification]`). Replace them with
  your contract's prices.
- Wrong answers are usually a neighbouring label (a pilot called an implementation).

## Sources
- The vendor covers 82% of companies.
- Headcount is noisy by ±18%.
- Rounds appear 3–45 days after announcement, misdated in 10% of cases (15% held-out).
- 2% of rows are delivered twice, and 4% of companies have two vendor ids.
- The register covers 97% of DACH startups. It always carries the legal form, quotes contract dates and records
  name changes.
- The press writes 1–3 articles per relationship. 25% are vague (33% held-out) and 15% are German (25% held-out).
  20% noise articles name two companies with no relationship.
- The job board lists a company's open posts weekly by domain. Posts track headcount with ±25% weekly noise, and
  the page disappears after a shutdown.
- Two firms cannot share a name at the same seat (§30 HGB). The world applies this everywhere.

## People
- Reviewers are right.
- The time they spend is not modelled. The number of items they see is reported.

## Personal data
The vendor's `founder_email` stands for the personal data real vendor files carry. Nothing uses it. It is kept out
of everything below raw and removed from raw after 30 days, under GDPR Art. 5(1)(c) and (e).
