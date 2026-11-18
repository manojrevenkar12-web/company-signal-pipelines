-- A person's answers to the review queues. Kept across runs; every run applies them.
create table if not exists ops.review_decision (
    kind        text not null check (kind in ('pair', 'label', 'link')),
    subject     text not null,                 -- 'record_a|record_b', or an article url
    answer      text not null,                 -- same | different, a label, or an entity id
    decided_by  text not null,
    decided_at  timestamptz not null default now(),
    primary key (kind, subject)
);
