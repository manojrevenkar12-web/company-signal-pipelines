-- The raw layer: every delivery as it arrived, keyed so a redelivery adds nothing.
create schema if not exists raw;
create schema if not exists core;
create schema if not exists ops;

create table if not exists raw.load_run (
    id            bigserial primary key,
    feed          text not null,
    delivery_day  int not null,          -- the day the file belongs to
    kind          text not null check (kind in ('scheduled', 'backfill')),
    hour          int not null,          -- hours since the run's first day 00:00 when it was loaded
    rows          int not null,
    new_rows      int not null default 0,
    status        text not null check (status in ('loaded', 'quarantined')),
    note          text not null default '',
    loaded_at     timestamptz not null default now()
);

create table if not exists raw.record (
    id            bigserial primary key,
    feed          text not null,
    source_key    text not null,
    payload_hash  text not null,
    payload       jsonb not null,
    delivery_day  int not null,
    loaded_hour   int not null,
    run_id        bigint not null references raw.load_run (id),
    unique (feed, source_key, payload_hash)
);
create index if not exists record_feed_key on raw.record (feed, source_key);

-- A delivery whose shape broke its contract is kept aside, never read downstream.
create table if not exists raw.quarantine (
    run_id   bigint primary key references raw.load_run (id),
    feed     text not null,
    payload  jsonb not null
);
