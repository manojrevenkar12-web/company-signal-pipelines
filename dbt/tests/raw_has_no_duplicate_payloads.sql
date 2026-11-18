select feed, source_key, payload_hash from {{ source('raw', 'record') }}
group by 1, 2, 3 having count(*) > 1
