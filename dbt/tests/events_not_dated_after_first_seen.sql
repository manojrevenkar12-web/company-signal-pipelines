-- An event cannot be dated after the pipeline first saw evidence of it.
select event_id from {{ ref('company_signals') }} where days_until_known < 0
