-- =============================================================================
-- Migration: GCI v2.0 Schema — Milestone 1 (Schema Only, No Data)
-- File:      migrations/2026-05_gci_v2_schema.sql
-- Spec:      SPEC_GCI_v2_0_M1_schema_migration.md
-- Commit:    feat: add GCI v2.0 schema (grid_constraint, infrastructure_raw, constraint enums)
--
-- ADDITIVE ONLY: creates new objects, touches NOTHING existing.
-- IDEMPOTENT:    safe to run multiple times without side effects.
--
-- Pre-flight results (2026-05):
--   methodology_versions columns: version, description, published_at, methodology_url
--     → no params JSONB column; params documented in description text + raw_components
--   Spatial functions available:
--     core.find_region_for_point(pt geometry)       → point → region_id
--     infrastructure.powerlines_set_regions()       → trigger fn, line → region_ids[]
--   infrastructure.powerlines geometry: LINESTRING, SRID 4326
--   DC enums: infrastructure.dc_status, infrastructure.geocoding_precision  ✓
--   grid_feasibility_current: 133 rows (live path intact)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- §3. Methodology version: gci-v2.0-energy-county
--     v1.0 row is left untouched (historical archive).
--     No params JSONB column exists in methodology_versions →
--       parameters are documented here in description text.
--       Per-snapshot calibrated values will be stored in
--       grid_constraint.raw_components.params_used at recompute (milestone 2).
-- -----------------------------------------------------------------------------
insert into indices.methodology_versions (version, description, published_at, methodology_url)
values (
  'gci-v2.0-energy-county',
  'Grid Constraint Index v2.0. Vector of 4 transparent axes — '
  '(1) supply deliverability [structural], '
  '(2) interconnection contention [dynamic], '
  '(3) compute concentration [concentration], '
  '(4) externality exposure [realized] — '
  'each with own confidence tier. '
  'Headline category = worst-of available axis (weight-free). '
  'Measures structural constraint, never models power flows. '
  'Scope: county-level, Virginia pilot (133 counties). '
  'Documented parameters (calibrated values stored per-snapshot in '
  'grid_constraint.raw_components.params_used): '
  'completion_rate_by_iso, transmission_derating_factor, import_cap_pct, '
  'dc_backup_gen_to_load_factor, tier_thresholds_per_axis.',
  now(),
  null
)
on conflict (version) do nothing;


-- -----------------------------------------------------------------------------
-- §4.1. New enum: indices.constraint_category
--
-- ORDER IS LOAD-BEARING — do not change.
-- worst-of headline in milestone 2 uses max(tier) over available axes,
-- relying on Postgres native enum ordering. 'severe' must be last so that
-- max() returns it as the worst. Any reordering breaks worst-of logic.
-- -----------------------------------------------------------------------------
do $$ begin
  create type indices.constraint_category as enum
    ('favorable', 'moderate', 'emerging', 'severe');
exception when duplicate_object then null; end $$;


-- -----------------------------------------------------------------------------
-- §4.2. New enum: indices.confidence_tier
--
-- Semantics:
--   high         → direct measurement (EIA-860 generation, VA DC inventory)
--   medium       → contention (queue × completion rate)
--   proxy_heavy  → axis 1 entirely (Import_proxy / transmission uncertainty)
--   sparse       → data exists but thin (DC concentration outside VA)
--   absent       → no data; axis excluded from worst-of
-- -----------------------------------------------------------------------------
do $$ begin
  create type indices.confidence_tier as enum
    ('high', 'medium', 'proxy_heavy', 'sparse', 'absent');
exception when duplicate_object then null; end $$;


-- -----------------------------------------------------------------------------
-- §5. Main table: indices.grid_constraint
--
-- INSERT-only time-series, parallel to grid_feasibility.
-- NOT a replacement — old grid_feasibility is the historical v1.0 archive.
-- Architecture decision: clean separation, simpler migration (§3.2 handoff).
--
-- Null axes: axis without data → *_value/*_tier/*_confidence = NULL
--   (or confidence = 'absent'). Excluded from worst-of (milestone 2 logic).
-- headline_category / headline_confidence are NOT NULL: for VA all 4 axes
--   are available; for Phase B national axes 1–2 are always computable.
--
-- raw_components JSONB documented structure (filled at recompute, milestone 2):
-- {
--   "axis1_supply":        { "net_summer_gen_mw": null, "import_proxy_mw": null,
--                            "peak_adj_mw": null, "existing_load_adjustment_mw": null,
--                            "deliverable_mw": null },
--   "axis2_contention":    { "queue_mw": null, "completion_rate": null,
--                            "contention_mw": null, "iso": null },
--   "axis3_concentration": { "operating_dc_load_mw": null, "dc_facility_count": null },
--   "axis4_externality":   { "indicators": [], "magnitude": null },
--   "transmission":        { "inbound_lines_count": null, "raw_thermal_mw": null,
--                            "derating_factor": null, "cap_pct": null },
--   "params_used":         { "completion_rate_by_iso": null,
--                            "transmission_derating_factor": null,
--                            "import_cap_pct": null,
--                            "dc_backup_gen_to_load_factor": null,
--                            "tier_thresholds": null }
-- }
-- -----------------------------------------------------------------------------
create table if not exists indices.grid_constraint (
  id                               uuid primary key default gen_random_uuid(),
  region_id                        uuid not null references core.regions(id),
  methodology_version              text not null
                                     references indices.methodology_versions(version),
  computed_at                      timestamptz not null default now(),

  -- Headline: worst-of result across available axes
  headline_category                indices.constraint_category not null,
  headline_confidence              indices.confidence_tier     not null,

  -- Axis 1: Supply deliverability (Structural)
  local_adequacy_ratio             numeric,   -- Deliverable / Peak_adj, floored at 0
  deficit_severity                 numeric,   -- signed (NetGen+Import−Peak)/Peak
  supply_tier                      indices.constraint_category,
  supply_confidence                indices.confidence_tier,

  -- Axis 2: Interconnection contention (Dynamic)
  interconnection_contention       numeric,   -- contention / Peak_adj
  contention_tier                  indices.constraint_category,
  contention_confidence            indices.confidence_tier,

  -- Axis 3: Compute concentration (Concentration)
  compute_concentration            numeric,   -- operating_DC_load_MW / Peak_adj
  concentration_tier               indices.constraint_category,
  concentration_confidence         indices.confidence_tier,

  -- Axis 4: Externality exposure (Realized)
  externality_exposure             numeric,   -- magnitude indicator
  externality_tier                 indices.constraint_category,
  externality_confidence           indices.confidence_tier,

  -- Transmission accessibility: INPUT to axis 1 only.
  -- Exposed as a separate toggleable map layer.
  -- NOT a standalone worst-of axis (methodology §3.1).
  -- Its unreliability is absorbed into supply_confidence = proxy_heavy.
  transmission_accessibility_score numeric,

  -- Raw formula inputs + params used in this snapshot (reproducibility).
  -- Full documented structure in comments above.
  raw_components                   jsonb not null default '{}'::jsonb,

  -- Per-county annotation flags (e.g. 'ERCOT: import minimal by design')
  notes                            text,

  constraint grid_constraint_uniq
    unique (region_id, methodology_version, computed_at),
  constraint adequacy_ratio_nonneg
    check (local_adequacy_ratio is null or local_adequacy_ratio >= 0)
);

create index if not exists idx_grid_constraint_region
  on indices.grid_constraint (region_id);

create index if not exists idx_grid_constraint_region_time
  on indices.grid_constraint (region_id, computed_at desc);

create index if not exists idx_grid_constraint_headline
  on indices.grid_constraint (headline_category);


-- -----------------------------------------------------------------------------
-- §5.1. View: indices.grid_constraint_current
--
-- Latest snapshot per region. Mirrors grid_feasibility_current pattern.
-- Frontend can read this when v2.0 switch happens (future milestone).
-- create or replace is safe — no existing view with this name.
-- -----------------------------------------------------------------------------
create or replace view indices.grid_constraint_current as
select distinct on (region_id) *
from indices.grid_constraint
order by region_id, computed_at desc;


-- -----------------------------------------------------------------------------
-- §5.2. Grants — mirrors grid_feasibility grants (public read-only tracker)
-- RLS stays disabled per §4.4 ARCHITECTURE_DECISIONS.
-- Schema indices is already exposed in Data API.
-- Live frontend code does NOT query these until the future switch milestone.
-- -----------------------------------------------------------------------------
grant select on indices.grid_constraint         to anon, authenticated;
grant select on indices.grid_constraint_current to anon, authenticated;


-- =============================================================================
-- §6. New schema: infrastructure_raw
--
-- Isolated from live infrastructure schema.
-- NOT exposed in Data API (no anon grants).
-- Bulk ingestion via direct psycopg2 under service credentials only.
-- Heavy geometry (lines, substations) reaches frontend via vector tiles
-- (Tippecanoe → .pmtiles → R2), not PostgREST.
-- =============================================================================
create schema if not exists infrastructure_raw;


-- -----------------------------------------------------------------------------
-- §6.6 (declared first) — shared trigger function for POINT tables
--
-- Calls core.find_region_for_point() — the existing canonical spatial function.
-- This is a thin trigger adapter (no spatial logic here), not a new spatial fn.
-- Reused by all four point tables below.
-- -----------------------------------------------------------------------------
create or replace function infrastructure_raw.set_region_from_point()
returns trigger
language plpgsql
as $$
begin
  if new.geom is not null then
    new.region_id := core.find_region_for_point(new.geom);
  end if;
  return new;
end;
$$;


-- -----------------------------------------------------------------------------
-- §6.1. infrastructure_raw.power_plants — EIA-860 net summer capacity
--
-- Fresh table for clean EIA-860 ingestion (net SUMMER capacity, not nameplate).
-- Old infrastructure.power_plants is left untouched as historical.
-- Deliberate duplication for additive safety and clean v1/v2 separation.
-- Reconciliation / deprecation of the old table → separate future cleanup SPEC.
-- -----------------------------------------------------------------------------
create table if not exists infrastructure_raw.power_plants (
  id                       uuid primary key default gen_random_uuid(),
  source                   text    not null,
  source_id                text    not null,
  plant_name               text,
  net_summer_capacity_mw   numeric,
  prime_mover              text,
  fuel_type                text,
  geom                     geometry(Point, 4326),
  region_id                uuid    references core.regions(id),
  raw_attributes           jsonb,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  constraint power_plants_source_uniq unique (source, source_id)
);

create index if not exists idx_iraw_power_plants_geom
  on infrastructure_raw.power_plants using gist (geom);
create index if not exists idx_iraw_power_plants_region
  on infrastructure_raw.power_plants (region_id);

drop trigger if exists trg_power_plants_set_region
  on infrastructure_raw.power_plants;
create trigger trg_power_plants_set_region
  before insert or update on infrastructure_raw.power_plants
  for each row execute function infrastructure_raw.set_region_from_point();


-- -----------------------------------------------------------------------------
-- §6.2. infrastructure_raw.transmission_lines — HIFLD lines + ORNL DLR
--
-- Geometry type matches infrastructure.powerlines (confirmed pre-flight):
--   LINESTRING, SRID 4326.
-- region_ids[] auto-populated by reused trigger function
--   infrastructure.powerlines_set_regions() (pre-flight confirmed it exists).
-- Trigger functions in Postgres are reusable across tables; direct reuse is
--   valid because our column name (region_ids uuid[]) matches the original.
-- -----------------------------------------------------------------------------
create table if not exists infrastructure_raw.transmission_lines (
  id               uuid primary key default gen_random_uuid(),
  source           text    not null,
  source_id        text    not null,
  voltage_kv       numeric,
  dlr_thermal_mw   numeric,   -- ORNL Hourly DLR join value
  geom             geometry(LineString, 4326),
  region_ids       uuid[],    -- auto-populated by trigger below
  raw_attributes   jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint transmission_lines_source_uniq unique (source, source_id)
);

create index if not exists idx_iraw_transmission_lines_geom
  on infrastructure_raw.transmission_lines using gist (geom);

drop trigger if exists trg_transmission_lines_set_region
  on infrastructure_raw.transmission_lines;
create trigger trg_transmission_lines_set_region
  before insert or update on infrastructure_raw.transmission_lines
  for each row execute function infrastructure.powerlines_set_regions();


-- -----------------------------------------------------------------------------
-- §6.3. infrastructure_raw.substations
-- -----------------------------------------------------------------------------
create table if not exists infrastructure_raw.substations (
  id               uuid primary key default gen_random_uuid(),
  source           text    not null,
  source_id        text    not null,
  name             text,
  pnode_id         text,    -- business-key link to pnodes table
  geom             geometry(Point, 4326),
  region_id        uuid    references core.regions(id),
  raw_attributes   jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint substations_source_uniq unique (source, source_id)
);

create index if not exists idx_iraw_substations_geom
  on infrastructure_raw.substations using gist (geom);
create index if not exists idx_iraw_substations_region
  on infrastructure_raw.substations (region_id);

drop trigger if exists trg_substations_set_region
  on infrastructure_raw.substations;
create trigger trg_substations_set_region
  before insert or update on infrastructure_raw.substations
  for each row execute function infrastructure_raw.set_region_from_point();


-- -----------------------------------------------------------------------------
-- §6.4. infrastructure_raw.pnodes — LMP price nodes
--
-- LMP congestion time-series intentionally NOT created in this milestone.
-- Its schema depends on ISO-CSV structure not yet finalised → separate SPEC.
-- Congestion values sit in raw_attributes for now.
-- -----------------------------------------------------------------------------
create table if not exists infrastructure_raw.pnodes (
  id               uuid primary key default gen_random_uuid(),
  source           text    not null,
  source_id        text    not null,   -- ISO pnode id (business key)
  pnode_name       text,
  iso              text,
  geom             geometry(Point, 4326),
  substation_id    uuid    references infrastructure_raw.substations(id),
  region_id        uuid    references core.regions(id),
  raw_attributes   jsonb,              -- may hold congestion values at this stage
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint pnodes_source_uniq unique (source, source_id)
);

create index if not exists idx_iraw_pnodes_geom
  on infrastructure_raw.pnodes using gist (geom);
create index if not exists idx_iraw_pnodes_region
  on infrastructure_raw.pnodes (region_id);

drop trigger if exists trg_pnodes_set_region
  on infrastructure_raw.pnodes;
create trigger trg_pnodes_set_region
  before insert or update on infrastructure_raw.pnodes
  for each row execute function infrastructure_raw.set_region_from_point();


-- -----------------------------------------------------------------------------
-- §6.5. infrastructure_raw.dc_inventory — analytical capacity inventory
--
-- Feeds axes 3, 4 and Existing_Load_Adjustment.
-- SOURCE: air-permit registries ("Franklin pilot method").
--
-- IMPORTANT DISTINCTION:
--   This table  = analytical capacity inventory (air-permit / DEQ data)
--   infrastructure.datacenters_* = OSM/Epoch visual display layers
--   They are separate by design. Do NOT conflate.
--
-- cap_source documents provenance of capacity_mw:
--   'DEQ_backup_gen' → capacity = backup generator MW from air-permit,
--   NOT IT-load (see methodology §5/§4 for conversion factors).
--
-- Reuses infrastructure.dc_status and infrastructure.geocoding_precision
-- enums (pre-flight confirmed both exist). No new enums created.
--
-- has_geometry mirrors the Epoch-pattern from Phase A3.
-- -----------------------------------------------------------------------------
create table if not exists infrastructure_raw.dc_inventory (
  id                   uuid primary key default gen_random_uuid(),
  source               text    not null,   -- e.g. 'VA_DEQ', 'OSM'
  source_id            text    not null,
  name                 text,
  operator             text,
  status               infrastructure.dc_status,
  capacity_mw          numeric,
  cap_source           text,              -- e.g. 'DEQ_backup_gen'
  geocoding_precision  infrastructure.geocoding_precision,
  geom                 geometry(Point, 4326),
  region_id            uuid    references core.regions(id),
  has_geometry         boolean generated always as (geom is not null) stored,
  raw_attributes       jsonb,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint dc_inventory_source_uniq unique (source, source_id)
);

create index if not exists idx_iraw_dc_inventory_geom
  on infrastructure_raw.dc_inventory using gist (geom);
create index if not exists idx_iraw_dc_inventory_region
  on infrastructure_raw.dc_inventory (region_id);

drop trigger if exists trg_dc_inventory_set_region
  on infrastructure_raw.dc_inventory;
create trigger trg_dc_inventory_set_region
  before insert or update on infrastructure_raw.dc_inventory
  for each row execute function infrastructure_raw.set_region_from_point();


-- =============================================================================
-- END OF MIGRATION
-- Run 2026-05_gci_v2_verify.sql to confirm acceptance criteria.
-- =============================================================================
