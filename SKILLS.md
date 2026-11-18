# SKILLS.md

Repeatable tasks and the commands that do them.

## Add a feed
1. Add `[feeds.<name>]` to `config/pipelines.toml`: description, SLA in hours, cost per record, key, cadence in
   days and required fields.
2. Write a `<name>_records` builder in `src/signals/resolve/records.py` if the feed describes companies. Write an
   evidence function in `src/signals/events/detect.py` if it carries signals.
3. Add `dbt/models/staging/stg_<name>.sql`. Select only the fields you use; personal fields stay in raw.
4. Teach the world to deliver it (`world/generate.py`) and add an outage for it to both world configs.
5. Run `make test eval report`.

## Tune a threshold
1. Change it in `config/pipelines.toml` and note in a comment which dev seed it was set on.
2. Run `make eval report` and compare the ablation table before and after.
3. Never tune on the held-out world.

## Add a design or an ablation
Add a table to `config/designs.toml` that overrides `[platform]` switches. Then run `make eval report`.

## Work the review queues
`GET /review` lists doubtful company pairs and unsure labels. To answer:

- `POST /review/pairs` with `{record_a, record_b, answer: same|different}`;
- `POST /review/labels` with `{url, label}`;
- send an `X-Reviewer` header with either.

Answers go to `ops.review_decision` and are applied on the next run.

## Run the production path locally
1. `make demo`: landing files, then Postgres raw and core, then `dbt build`.
2. `make api`, and in `web/` run `npm run dev`.
3. `dagster dev -m signals.orchestration` runs the daily partitions and sensors.

## Classify real articles with Claude
Set `ANTHROPIC_API_KEY` and run `signals classify articles.json`. The answers pass through the same cascade and the
same code checks as in production.

## Remove personal data past retention
Run `signals redact --days 30`. Schedule it daily in production.

## Run the held-out world
Run `make heldout`, once. Then run `make report` and commit `reports/heldout.json` with the lock.
