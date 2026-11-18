{% test dbt_utils_free_unique_pair(model) %}
select corporate_entity, startup_entity, count(*)
from {{ model }}
group by 1, 2
having count(*) > 1
{% endtest %}
