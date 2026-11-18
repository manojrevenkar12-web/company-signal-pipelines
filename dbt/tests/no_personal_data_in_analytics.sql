-- No column below raw carries an e-mail address.
select table_schema, table_name, column_name
from information_schema.columns
where table_schema in ('staging', 'analytics', 'core')
  and (column_name ilike '%email%' or column_name ilike '%founder%')
