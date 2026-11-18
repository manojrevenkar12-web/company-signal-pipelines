select
    source_key                     as notice_id,
    payload ->> 'court'            as court,
    payload ->> 'register_no'      as register_no,
    payload ->> 'company_name'     as company_name,
    payload ->> 'seat'             as seat,
    payload ->> 'country'          as country,
    (payload ->> 'published_on')::date as published_on,
    payload ->> 'kind'             as notice_kind,
    payload ->> 'text'             as notice_text,
    delivery_day
from {{ source('raw', 'record') }}
where feed = 'register_notices'
