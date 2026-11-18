-- The golden record: one row per company, each field with the source that won.
with f as (select * from {{ source('core', 'field_value') }})
select
    e.entity_id,
    e.is_customer,
    e.members                                                             as source_records,
    max(f.value) filter (where f.field = 'name')                          as name,
    max(f.source) filter (where f.field = 'name')                         as name_source,
    max(f.value) filter (where f.field = 'domain')                        as domain,
    max(f.value) filter (where f.field = 'city')                          as city,
    max(f.value) filter (where f.field = 'country')                       as country,
    max(f.value) filter (where f.field = 'founded')::int                  as founded_year,
    max(f.value) filter (where f.field = 'headcount')::int                as headcount,
    coalesce(max(f.value) filter (where f.field = 'status'), 'active')    as status,
    max(f.source) filter (where f.field = 'status')                       as status_source,
    max(f.observed) filter (where f.field = 'status')                     as status_observed
from {{ source('core', 'entity') }} e
left join f on f.entity_id = e.entity_id
group by e.entity_id, e.is_customer, e.members
