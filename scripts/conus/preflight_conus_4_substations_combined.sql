-- preflight_conus_4_substations_combined.sql
-- Все три проверки в одном result set (Supabase Editor иначе показывает
-- только последний запрос при выполнении файла целиком).

select 'substations.columns' as check_name,
       coalesce(
         string_agg(column_name || ':' || data_type, ', ' order by ordinal_position),
         '(таблица/колонки не найдены)'
       ) as result
from information_schema.columns
where table_schema = 'infrastructure' and table_name = 'substations'

union all

select 'substations.count_and_bbox',
       concat(
         c.total_substations, ' rows',
         ' / bbox: xmin=', round(st_xmin(b.ext)::numeric, 2),
         ' ymin=', round(st_ymin(b.ext)::numeric, 2),
         ' xmax=', round(st_xmax(b.ext)::numeric, 2),
         ' ymax=', round(st_ymax(b.ext)::numeric, 2)
       )
from (select count(*) as total_substations from infrastructure.substations) c
cross join (select st_extent(geometry) as ext from infrastructure.substations) b

union all

select 'substations.west_of_va (lon < -84)',
       count(*)::text
from infrastructure.substations
where st_x(geometry) < -84

order by check_name;
