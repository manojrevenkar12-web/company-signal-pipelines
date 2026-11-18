-- One row per vendor profile, latest delivery wins. founder_email is personal data we do not use: not selected.
with ranked as (
    select
        source_key as vendor_id,
        payload,
        delivery_day,
        row_number() over (partition by source_key order by delivery_day desc, loaded_hour desc, id desc) as rn
    from {{ source('raw', 'record') }}
    where feed = 'vendor_profiles'
)
select
    vendor_id,
    payload ->> 'name'                        as name,
    payload ->> 'domain'                      as domain_raw,
    payload ->> 'city'                        as city,
    payload ->> 'country'                     as country,
    (payload ->> 'founded_year')::int         as founded_year,
    (payload ->> 'headcount')::int            as headcount,
    payload ->> 'status'                      as vendor_status,
    jsonb_array_length(coalesce(payload -> 'funding_rounds', '[]'::jsonb)) as funding_rounds,
    delivery_day
from ranked
where rn = 1
