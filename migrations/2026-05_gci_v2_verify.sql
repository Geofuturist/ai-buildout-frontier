-- =============================================================================
-- Verification: GCI v2.0 Schema — Milestone 1
-- File: migrations/2026-05_gci_v2_verify.sql
-- Run AFTER 2026-05_gci_v2_schema.sql
--
-- Acceptance criteria:
--   Query 1  → both versions present
--   Query 2  → enum order exactly: favorable→moderate→emerging→severe
--   Query 3  → all 6 new tables + 1 view exist
--   Query 4  → 5 triggers on infrastructure_raw tables
--   Query 5  → live path untouched: 133/133 rows, feasibility_category enum intact
--   Query 6  → new tables empty (schema only, no data loaded)
-- =============================================================================


-- 1. Both methodology versions present; v1.0 historical row intact
select version, left(description, 60) as description_preview, published_at
from indices.methodology_versions
order by published_at;
-- Expected: two rows — 'v1.0' and 'gci-v2.0-energy-county'


-- 2. New enum values with correct ordering
--    constraint_category must be: favorable(1) < moderate(2) < emerging(3) < severe(4)
--    confidence_tier must be:     high(1) < medium(2) < proxy_heavy(3) < sparse(4) < absent(5)
select t.typname, e.enumlabel, e.enumsortorder
from pg_type t
join pg_enum e on e.enumtypid = t.oid
join pg_namespace n on n.oid = t.typnamespace
where n.nspname = 'indices'
  and t.typname in ('constraint_category', 'confidence_tier')
order by t.typname, e.enumsortorder;


-- 3a. New tables exist in indices and infrastructure_raw
select table_schema, table_name
from information_schema.tables
where table_schema in ('indices', 'infrastructure_raw')
  and table_name in (
    'grid_constraint',
    'power_plants',
    'transmission_lines',
    'substations',
    'pnodes',
    'dc_inventory'
  )
order by table_schema, table_name;
-- Expected: 6 rows

-- 3b. View exists
select table_name, view_definition is not null as has_definition
from information_schema.views
where table_schema = 'indices'
  and table_name = 'grid_constraint_current';
-- Expected: 1 row


-- 4. Spatial triggers on 5 new infrastructure_raw tables
select event_object_schema, event_object_table, trigger_name, event_manipulation
from information_schema.triggers
where event_object_schema = 'infrastructure_raw'
order by event_object_table, event_manipulation;
-- Expected: rows for power_plants, substations, pnodes, dc_inventory (point fn),
--           transmission_lines (line fn) — at least 5 trigger entries


-- 5. ADDITIVITY CHECK — live v1.0 path completely untouched
select count(*) as v1_rows          from indices.grid_feasibility_current;
-- Expected: 133

select count(*) as region_rows      from core.regions;
-- Expected: 133

select 'feasibility_category enum intact' as check_name
where exists (
  select 1
  from pg_type t
  join pg_namespace n on n.oid = t.typnamespace
  where n.nspname = 'indices' and t.typname = 'feasibility_category'
);
-- Expected: 1 row with 'feasibility_category enum intact'


-- 6. New tables are empty (schema-only milestone, no data loaded)
select 'grid_constraint'    as table_name, count(*) as row_count from indices.grid_constraint
union all
select 'power_plants',                     count(*) from infrastructure_raw.power_plants
union all
select 'transmission_lines',               count(*) from infrastructure_raw.transmission_lines
union all
select 'substations',                      count(*) from infrastructure_raw.substations
union all
select 'pnodes',                           count(*) from infrastructure_raw.pnodes
union all
select 'dc_inventory',                     count(*) from infrastructure_raw.dc_inventory
order by table_name;
-- Expected: all rows show count = 0
