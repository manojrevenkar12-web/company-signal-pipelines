-- Corporate-startup relationships, strongest label per pair; only labels a rule, a model or a person accepted.
with labelled as (
    select
        corporate_entity,
        startup_entity,
        label,
        decided_by,
        published_on,
        case label
            when 'acquisition' then 6 when 'investment' then 5 when 'implementation' then 4
            when 'poc' then 3 when 'partnership' then 2 when 'mention' then 1 else 0 end as strength
    from {{ source('core', 'article') }}
    where decided_by <> 'review' and corporate_entity is not null and startup_entity is not null
      and label <> 'none'
)
select
    corporate_entity,
    startup_entity,
    (array_agg(label order by strength desc, published_on desc))[1] as relationship,
    count(*)                                                         as articles,
    min(published_on)                                                as first_seen,
    max(published_on)                                                as last_seen
from labelled
group by corporate_entity, startup_entity
