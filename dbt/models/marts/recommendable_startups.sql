-- What the scouting product may recommend: startups that still exist independently.
select entity_id, name, domain, city, country, founded_year, headcount
from {{ ref('companies') }}
where not is_customer
  and status = 'active'
  and name is not null
