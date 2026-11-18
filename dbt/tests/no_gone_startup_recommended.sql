-- A startup the register, the press or the vendor says was acquired or shut down is never recommendable.
select r.entity_id
from {{ ref('recommendable_startups') }} r
join {{ ref('companies') }} c using (entity_id)
where c.status in ('acquired', 'shut_down')
