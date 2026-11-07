{# Fails on any repeated combination of the given columns. #}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as copies
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{# Fails when a series skips a month between its first and last month. #}
{% test no_month_gaps(model, partition_by) %}
{% set keys = partition_by | join(', ') %}
select {{ keys ~ ',' if keys }} count(*) as months_present,
    {{ dbt.datediff('min(month)', 'max(month)', 'month') }} + 1 as months_expected
from {{ model }}
{% if keys %}group by {{ keys }}{% endif %}
having count(*) <> {{ dbt.datediff('min(month)', 'max(month)', 'month') }} + 1
{% endtest %}
