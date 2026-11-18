-- Identifiers decide: two register numbers or two CRM ids never end up in one company.
select entity_id
from {{ source('core', 'source_record') }}
where identifier is not null
group by entity_id
having count(distinct identifier) > 1
