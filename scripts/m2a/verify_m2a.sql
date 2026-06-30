-- Verification: GCI v2.0 Milestone 2a — выполнить после всех 4 ingestion-скриптов
-- SPEC_GCI_v2_0_M2a_pipeline.md §8

-- 1. Ingestion непустой и в нужных регионах
select count(*) as power_plants_with_region
from infrastructure_raw.power_plants where region_id is not null;

select count(*) as transmission_lines_total
from infrastructure_raw.transmission_lines;

select count(*) as queue_pjm
from infrastructure_raw.interconnection_queue where iso = 'PJM';

select count(*) as dc_operational
from infrastructure_raw.dc_inventory where status = 'operational';

-- 2. АДДИТИВНОСТЬ: live v1.0 цел, grid_constraint пуста (2a сюда НЕ пишет)
select count(*) as v1_live_path from indices.grid_feasibility_current;  -- ожидается 133
select count(*) as grid_constraint_rows from indices.grid_constraint;    -- ожидается 0

-- 3. Распределение по округам — быстрая визуальная проверка
select
  r.admin_code as fips, r.name,
  count(pp.id) as n_plants,
  coalesce(sum(pp.net_summer_capacity_mw), 0) as net_summer_mw
from core.regions r
left join infrastructure_raw.power_plants pp on pp.region_id = r.id
where r.admin_code like '51%'
group by r.admin_code, r.name
order by net_summer_mw desc
limit 15;
