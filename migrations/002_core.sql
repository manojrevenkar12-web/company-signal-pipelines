-- What the pipelines decided. Rebuilt on every run from raw; raw is never edited.
create extension if not exists pg_trgm;

create table if not exists core.source_record (
    record_id   text primary key,            -- '<feed>:<key>'
    feed        text not null,
    names       text[] not null default '{}',
    domain      text,
    city        text,
    country     text,
    founded     int,
    identifier  text,                         -- register number or CRM id: never two companies
    entity_id   text not null
);

create table if not exists core.entity (
    entity_id    text primary key,
    is_customer  boolean not null default false,
    members      int not null
);

create table if not exists core.entity_name (
    entity_id  text not null references core.entity (entity_id),
    name       text not null,
    name_key   text not null,
    is_golden  boolean not null default false,
    primary key (entity_id, name)
);
create index if not exists entity_name_trgm on core.entity_name using gin (name_key gin_trgm_ops);

create table if not exists core.review_pair (
    record_a   text not null,
    record_b   text not null,
    score      numeric(5, 4) not null,
    reason     text not null,
    decision   text check (decision in ('same', 'different')),
    decided_by text,
    decided_at timestamptz,
    primary key (record_a, record_b)
);

create table if not exists core.article (
    url              text primary key,
    published_on     date,
    language         text,
    title            text,
    corporate_entity text,
    startup_entity   text,
    link_status      text not null,
    candidates       text[] not null default '{}',
    label            text not null,
    decided_by       text not null check (decided_by in ('rule', 'cheap', 'expensive', 'review', 'person')),
    confidence       numeric(5, 4) not null,
    cost_eur         numeric(10, 6) not null,
    steps            text not null
);

create table if not exists core.event (
    event_id   text primary key,
    entity_id  text not null references core.entity (entity_id),
    kind       text not null check (kind in ('funding', 'acquisition', 'shutdown', 'headcount')),
    event_date date not null,
    sources    text[] not null
);

create table if not exists core.event_evidence (
    event_id  text not null references core.event (event_id),
    source    text not null,
    ref       text not null,
    stated    date,
    seen      date not null
);

create table if not exists core.field_value (
    entity_id  text not null references core.entity (entity_id),
    field      text not null,
    value      text,
    source     text not null,
    observed   date not null,
    why        text not null,
    primary key (entity_id, field)
);

create table if not exists ops.alert (
    feed    text not null,
    kind    text not null,
    hour    int not null,
    day     int not null,
    detail  text not null,
    raised_at timestamptz not null default now(),
    primary key (feed, kind, hour)
);

create table if not exists ops.pipeline_run (
    id          bigserial primary key,
    design      text not null,
    started_at  timestamptz not null default now(),
    entities    int not null,
    articles    int not null,
    events      int not null,
    seconds     jsonb not null
);

