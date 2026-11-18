-- Per feed: loads, quarantined deliveries, backfills, rows kept and alerts raised.
with runs as (
    select feed,
           count(*) filter (where kind = 'scheduled' and status = 'loaded')  as loads,
           count(*) filter (where status = 'quarantined')                     as quarantined,
           count(*) filter (where kind = 'backfill')                          as backfills,
           sum(rows)                                                          as rows_delivered,
           sum(new_rows)                                                      as rows_kept,
           max(delivery_day)                                                  as last_day
    from {{ source('raw', 'load_run') }}
    group by feed
),
alerts as (
    select feed, count(*) as alerts, max(hour) as last_alert_hour
    from {{ source('ops', 'alert') }}
    group by feed
)
select r.*, coalesce(a.alerts, 0) as alerts, a.last_alert_hour,
       round(1 - r.rows_kept::numeric / nullif(r.rows_delivered, 0), 4) as redelivered_share
from runs r
left join alerts a using (feed)
