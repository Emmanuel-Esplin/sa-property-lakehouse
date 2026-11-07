{# Athena only: unload each mart to Parquet, so the cloud results can be compared locally.
   Marts are found from the project graph, so a new mart is exported without editing this. #}
{% macro export_marts() %}
  {% set bucket = env_var('LAKE_BUCKET') %}
  {% for node in graph.nodes.values()
       if node.resource_type == 'model' and 'marts' in node.fqn %}
    {% set sql %}
      unload (select * from {{ target.schema }}.{{ node.alias }})
      to 's3://{{ bucket }}/exports/dbt/{{ node.alias }}/'
      with (format = 'PARQUET', compression = 'SNAPPY')
    {% endset %}
    {% do run_query(sql) %}
    {{ log('Exported ' ~ node.alias, info=True) }}
  {% endfor %}
{% endmacro %}
