-- Dated signals with how many sources back each one.
select
    ev.event_id,
    ev.entity_id,
    c.name,
    c.domain,
    ev.kind,
    ev.event_date,
    array_length(ev.sources, 1)                    as source_count,
    ev.sources,
    min(x.seen)                                    as first_seen,
    min(x.seen) - ev.event_date                    as days_until_known
from {{ source('core', 'event') }} ev
join {{ ref('companies') }} c using (entity_id)
join {{ source('core', 'event_evidence') }} x using (event_id)
group by ev.event_id, ev.entity_id, c.name, c.domain, ev.kind, ev.event_date, ev.sources
