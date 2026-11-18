select
    source_key                         as post_week_domain,
    (payload ->> 'week_start')::date   as week_start,
    lower(payload ->> 'domain')        as domain,
    (payload ->> 'open_posts')::int    as open_posts,
    delivery_day
from {{ source('raw', 'record') }}
where feed = 'job_posts'
