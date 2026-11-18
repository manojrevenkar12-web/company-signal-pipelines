select distinct on (source_key)
    source_key                          as url,
    (payload ->> 'published_on')::date  as published_on,
    payload ->> 'language'              as language,
    payload ->> 'title'                 as title,
    payload ->> 'startup_domain'        as startup_domain,
    delivery_day
from {{ source('raw', 'record') }}
where feed = 'news_mentions'
order by source_key, delivery_day desc, id desc
