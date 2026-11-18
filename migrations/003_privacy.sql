-- Personal data: the vendor sends a founder e-mail we never use. It stays out of every table below raw and is
-- removed from raw after the retention window (GDPR Art. 5(1)(c) and (e): minimisation, storage limitation).
create or replace function raw.redact_personal(retention_days int) returns int
language sql as $$
    with done as (
        update raw.record
           set payload = payload - 'founder_email'
         where payload ? 'founder_email'
           and run_id in (select id from raw.load_run where loaded_at < now() - make_interval(days => retention_days))
        returning 1
    )
    select count(*)::int from done;
$$;
