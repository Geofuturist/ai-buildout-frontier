-- =============================================================================
-- AI Buildout Frontier — Initial Database Schema
-- Version: v1.0
-- Created: 2026-04-21
-- =============================================================================
--
-- This script creates the full database schema for the AI Buildout Frontier
-- tracker: 4 schemas (core, infrastructure, demand, indices) with tables,
-- indexes, triggers, and enums.
--
-- How to apply:
--   1. Open Supabase SQL Editor
--   2. Paste this entire file
--   3. Click "Run"
--   4. Expected: "Success. No rows returned."
--
-- Rollback: see end of file for DROP statements (commented out)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0. Prerequisites
-- -----------------------------------------------------------------------------

-- Ensure PostGIS is enabled (idempotent — safe to run even if already enabled)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable UUID generation (Supabase has this by default, but explicit is better)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- -----------------------------------------------------------------------------
-- 1. Schemas
-- -----------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS infrastructure;
CREATE SCHEMA IF NOT EXISTS demand;
CREATE SCHEMA IF NOT EXISTS indices;

COMMENT ON SCHEMA core IS 'Static administrative regions and reference data';
COMMENT ON SCHEMA infrastructure IS 'Physical energy infrastructure: substations, powerlines, plants';
COMMENT ON SCHEMA demand IS 'AI and datacenter capacity announcements';
COMMENT ON SCHEMA indices IS 'Computed metrics: Grid Feasibility Index with versioning';


-- -----------------------------------------------------------------------------
-- 2. Enum types
-- -----------------------------------------------------------------------------

-- Status of a power plant (GEM terminology)
CREATE TYPE infrastructure.plant_status AS ENUM (
  'operating',
  'construction',
  'pre-construction',
  'announced',
  'cancelled',
  'retired',
  'mothballed'
);

-- Status of a datacenter / AI capacity announcement
CREATE TYPE demand.announcement_status AS ENUM (
  'announced',
  'planned',
  'under_construction',
  'operational',
  'cancelled'
);

-- Grid Feasibility Index category
CREATE TYPE indices.feasibility_category AS ENUM (
  'high',
  'moderate',
  'low',
  'critical',
  'dc_hotspot'
);


-- -----------------------------------------------------------------------------
-- 3. core.regions — administrative boundaries
-- -----------------------------------------------------------------------------

CREATE TABLE core.regions (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name              text NOT NULL,
  country_code      text NOT NULL,                     -- ISO 3166-1 alpha-2: 'US', 'NO', 'AE', 'SA'
  admin_level       int NOT NULL CHECK (admin_level IN (1, 2)),
  admin_code        text,                              -- Native code: FIPS, fylke number, emirate code
  parent_region_id  uuid REFERENCES core.regions(id) ON DELETE SET NULL,
  geometry          geometry(MultiPolygon, 4326) NOT NULL,
  centroid          geometry(Point, 4326),             -- Auto-computed by trigger below
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),

  UNIQUE (country_code, admin_level, admin_code)
);

-- Spatial index: critical for ST_Within, ST_Intersects performance
CREATE INDEX regions_geometry_idx ON core.regions USING GIST (geometry);
CREATE INDEX regions_centroid_idx ON core.regions USING GIST (centroid);

-- Lookup indexes
CREATE INDEX regions_country_level_idx ON core.regions (country_code, admin_level);
CREATE INDEX regions_parent_idx ON core.regions (parent_region_id);

COMMENT ON TABLE core.regions IS 'Administrative boundaries (L1/L2). Static geometry + metadata only — no metrics.';
COMMENT ON COLUMN core.regions.admin_level IS '1=state/province/fylke, 2=county/district/emirate';
COMMENT ON COLUMN core.regions.admin_code IS 'Native administrative code (FIPS for US, fylke number for Norway, etc.)';


-- -----------------------------------------------------------------------------
-- 4. Helper function + trigger: auto-compute centroid
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION core.regions_compute_centroid()
RETURNS trigger AS $$
BEGIN
  NEW.centroid := ST_Centroid(NEW.geometry);
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER regions_centroid_trigger
  BEFORE INSERT OR UPDATE OF geometry ON core.regions
  FOR EACH ROW
  EXECUTE FUNCTION core.regions_compute_centroid();


-- -----------------------------------------------------------------------------
-- 5. Helper function: spatial join point to region
-- -----------------------------------------------------------------------------
-- Used by triggers below for substations and power_plants.
-- Finds the most specific region (highest admin_level) that contains the point.

CREATE OR REPLACE FUNCTION core.find_region_for_point(pt geometry)
RETURNS uuid AS $$
DECLARE
  result_id uuid;
BEGIN
  SELECT id INTO result_id
  FROM core.regions
  WHERE ST_Within(pt, geometry)
  ORDER BY admin_level DESC  -- Prefer L2 (county) over L1 (state) when both match
  LIMIT 1;
  RETURN result_id;
END;
$$ LANGUAGE plpgsql STABLE;


-- -----------------------------------------------------------------------------
-- 6. infrastructure.substations
-- -----------------------------------------------------------------------------

CREATE TABLE infrastructure.substations (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  geometry          geometry(Point, 4326) NOT NULL,
  region_id         uuid REFERENCES core.regions(id) ON DELETE SET NULL,
  voltage_kv        int,
  dc_relevance      int CHECK (dc_relevance BETWEEN 1 AND 4),
  source            text NOT NULL,                     -- 'OSM', 'HIFLD', 'GEM', etc.
  source_id         text,                              -- Original ID in source dataset
  raw_attributes    jsonb,                             -- All other attributes from source
  created_at        timestamptz NOT NULL DEFAULT now(),

  UNIQUE (source, source_id)                           -- Idempotency for ingestion
);

CREATE INDEX substations_geometry_idx ON infrastructure.substations USING GIST (geometry);
CREATE INDEX substations_region_idx ON infrastructure.substations (region_id);
CREATE INDEX substations_voltage_idx ON infrastructure.substations (voltage_kv);
CREATE INDEX substations_dc_relevance_idx ON infrastructure.substations (dc_relevance);

-- Auto-populate region_id on insert via spatial join
CREATE OR REPLACE FUNCTION infrastructure.substations_set_region()
RETURNS trigger AS $$
BEGIN
  IF NEW.region_id IS NULL THEN
    NEW.region_id := core.find_region_for_point(NEW.geometry);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER substations_region_trigger
  BEFORE INSERT ON infrastructure.substations
  FOR EACH ROW
  EXECUTE FUNCTION infrastructure.substations_set_region();

COMMENT ON TABLE infrastructure.substations IS 'Electrical substations from OSM/HIFLD. region_id auto-computed on insert.';
COMMENT ON COLUMN infrastructure.substations.dc_relevance IS '1=critical (HV backbone, 380+kV), 2=backbone, 3=regional, 4=sub-regional';


-- -----------------------------------------------------------------------------
-- 7. infrastructure.powerlines
-- -----------------------------------------------------------------------------
-- Note: powerlines can cross multiple regions, so region_ids is an array (uuid[]).

CREATE TABLE infrastructure.powerlines (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  geometry          geometry(LineString, 4326) NOT NULL,
  region_ids        uuid[],                            -- Array: regions this line crosses
  voltage_kv        int,
  dc_relevance      int CHECK (dc_relevance BETWEEN 1 AND 6),
  source            text NOT NULL,
  source_id         text,
  raw_attributes    jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),

  UNIQUE (source, source_id)
);

CREATE INDEX powerlines_geometry_idx ON infrastructure.powerlines USING GIST (geometry);
CREATE INDEX powerlines_region_ids_idx ON infrastructure.powerlines USING GIN (region_ids);
CREATE INDEX powerlines_voltage_idx ON infrastructure.powerlines (voltage_kv);

-- Auto-populate region_ids on insert
CREATE OR REPLACE FUNCTION infrastructure.powerlines_set_regions()
RETURNS trigger AS $$
BEGIN
  IF NEW.region_ids IS NULL OR array_length(NEW.region_ids, 1) IS NULL THEN
    SELECT array_agg(id) INTO NEW.region_ids
    FROM core.regions
    WHERE ST_Intersects(geometry, NEW.geometry);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER powerlines_regions_trigger
  BEFORE INSERT ON infrastructure.powerlines
  FOR EACH ROW
  EXECUTE FUNCTION infrastructure.powerlines_set_regions();

COMMENT ON TABLE infrastructure.powerlines IS 'Transmission lines from OSM. region_ids auto-computed (array: a line can cross multiple regions).';


-- -----------------------------------------------------------------------------
-- 8. infrastructure.power_plants
-- -----------------------------------------------------------------------------

CREATE TABLE infrastructure.power_plants (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  geometry             geometry(Point, 4326) NOT NULL,
  region_id            uuid REFERENCES core.regions(id) ON DELETE SET NULL,
  name                 text,
  capacity_mw          numeric,
  fuel_type            text,                           -- 'solar', 'gas', 'nuclear', 'hydro', etc.
  status               infrastructure.plant_status,
  commissioning_year   int,
  source               text NOT NULL,                  -- 'GEM', 'EIA', etc.
  source_id            text,
  raw_attributes       jsonb,
  created_at           timestamptz NOT NULL DEFAULT now(),

  UNIQUE (source, source_id)
);

CREATE INDEX power_plants_geometry_idx ON infrastructure.power_plants USING GIST (geometry);
CREATE INDEX power_plants_region_idx ON infrastructure.power_plants (region_id);
CREATE INDEX power_plants_fuel_idx ON infrastructure.power_plants (fuel_type);
CREATE INDEX power_plants_status_idx ON infrastructure.power_plants (status);

-- Auto-populate region_id on insert
CREATE OR REPLACE FUNCTION infrastructure.power_plants_set_region()
RETURNS trigger AS $$
BEGIN
  IF NEW.region_id IS NULL THEN
    NEW.region_id := core.find_region_for_point(NEW.geometry);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER power_plants_region_trigger
  BEFORE INSERT ON infrastructure.power_plants
  FOR EACH ROW
  EXECUTE FUNCTION infrastructure.power_plants_set_region();

COMMENT ON TABLE infrastructure.power_plants IS 'Power generation units from GEM/EIA. Capacity aggregated per station.';


-- -----------------------------------------------------------------------------
-- 9. demand.announcements
-- -----------------------------------------------------------------------------
-- Datacenters and AI capacity announcements. geometry nullable: some
-- announcements have no precise coordinates (only "Northern Virginia").

CREATE TABLE demand.announcements (
  id                          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  region_id                   uuid REFERENCES core.regions(id) ON DELETE SET NULL,
  geometry                    geometry(Point, 4326),
  project_name                text NOT NULL,
  operator                    text,                    -- 'AWS', 'Microsoft', 'G42', etc.
  announced_capacity_mw       numeric,
  status                      demand.announcement_status NOT NULL DEFAULT 'announced',
  announced_date              date,
  expected_operational_date   date,
  source_url                  text,
  source_description          text,
  raw_attributes              jsonb,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX announcements_geometry_idx ON demand.announcements USING GIST (geometry)
  WHERE geometry IS NOT NULL;
CREATE INDEX announcements_region_idx ON demand.announcements (region_id);
CREATE INDEX announcements_status_idx ON demand.announcements (status);
CREATE INDEX announcements_operator_idx ON demand.announcements (operator);

-- Auto-populate region_id if geometry provided but region_id not set
CREATE OR REPLACE FUNCTION demand.announcements_set_region()
RETURNS trigger AS $$
BEGIN
  IF NEW.region_id IS NULL AND NEW.geometry IS NOT NULL THEN
    NEW.region_id := core.find_region_for_point(NEW.geometry);
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER announcements_region_trigger
  BEFORE INSERT OR UPDATE ON demand.announcements
  FOR EACH ROW
  EXECUTE FUNCTION demand.announcements_set_region();

COMMENT ON TABLE demand.announcements IS 'AI/datacenter capacity announcements. Geometry nullable (some only have regional attribution).';


-- -----------------------------------------------------------------------------
-- 10. indices.methodology_versions
-- -----------------------------------------------------------------------------
-- Tracks the evolution of the Grid Feasibility Index methodology.
-- Every computed index row references a version here.

CREATE TABLE indices.methodology_versions (
  version           text PRIMARY KEY,                  -- 'v1.0', 'v1.1', 'v2.0'
  description       text NOT NULL,
  published_at      timestamptz NOT NULL DEFAULT now(),
  methodology_url   text                               -- Link to whitepaper or README section
);

COMMENT ON TABLE indices.methodology_versions IS 'Evolution of Grid Feasibility Index methodology. Every computed value references a version.';

-- Seed the initial version
INSERT INTO indices.methodology_versions (version, description, methodology_url)
VALUES (
  'v1.0',
  'Initial methodology. Feasibility = (headroom + substation_bonus − transmission_penalty − water_penalty) / (announced_queue × (1 − completion_rate)). Categories: high >=2.0, moderate 1.0-2.0, low 0.5-1.0, critical <0.5. DC hotspot override for Loudoun, Fairfax, Prince William, Arlington (VA) and Oslo (NO).',
  NULL
);


-- -----------------------------------------------------------------------------
-- 11. indices.grid_feasibility
-- -----------------------------------------------------------------------------
-- Time-series of computed Feasibility Index values.
-- Each (region, methodology_version, computed_at) is one row.
-- INSERT only — never UPDATE. History is a feature, not a side effect.

CREATE TABLE indices.grid_feasibility (
  id                    uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  region_id             uuid NOT NULL REFERENCES core.regions(id) ON DELETE CASCADE,
  methodology_version   text NOT NULL REFERENCES indices.methodology_versions(version),
  computed_at           timestamptz NOT NULL DEFAULT now(),
  value                 numeric NOT NULL,
  category              indices.feasibility_category NOT NULL,
  components            jsonb NOT NULL,                -- {available_capacity_mw, queue_pressure_mw, substation_bonus, transmission_penalty, ...}

  UNIQUE (region_id, methodology_version, computed_at)
);

-- Index for "current value" queries: ORDER BY computed_at DESC LIMIT 1
CREATE INDEX grid_feasibility_current_idx
  ON indices.grid_feasibility (region_id, methodology_version, computed_at DESC);

-- Index for time-series queries
CREATE INDEX grid_feasibility_computed_at_idx
  ON indices.grid_feasibility (computed_at DESC);

-- Index for category filtering (e.g., "show all critical regions")
CREATE INDEX grid_feasibility_category_idx
  ON indices.grid_feasibility (category);

COMMENT ON TABLE indices.grid_feasibility IS 'Time-series of Grid Feasibility Index. INSERT-only, versioned. History is a product feature.';
COMMENT ON COLUMN indices.grid_feasibility.components IS 'Component breakdown of the index value (for dashboard transparency tooltips)';


-- -----------------------------------------------------------------------------
-- 12. View: current feasibility (latest value per region per methodology)
-- -----------------------------------------------------------------------------
-- Convenience view for the dashboard: always returns the most recent value.

CREATE OR REPLACE VIEW indices.grid_feasibility_current AS
SELECT DISTINCT ON (region_id, methodology_version)
  id,
  region_id,
  methodology_version,
  computed_at,
  value,
  category,
  components
FROM indices.grid_feasibility
ORDER BY region_id, methodology_version, computed_at DESC;

COMMENT ON VIEW indices.grid_feasibility_current IS 'Latest computed value per (region, methodology). Use this in dashboard, not the raw table.';


-- -----------------------------------------------------------------------------
-- 13. Grant permissions for PostgREST auto-exposed API
-- -----------------------------------------------------------------------------
-- Supabase's Data API uses two roles:
--   - 'anon' = public (unauthenticated) requests
--   - 'authenticated' = logged-in users
-- For our read-only public tracker, we grant SELECT on everything to 'anon'.
-- Write operations go through service_role (bypasses RLS).

-- Schemas must be in Data API's exposed list. Supabase exposes 'public' by
-- default. We need to add our custom schemas via the UI:
--   Settings → Data API → Exposed schemas → add: core, infrastructure, demand, indices

-- Grant usage on schemas
GRANT USAGE ON SCHEMA core TO anon, authenticated;
GRANT USAGE ON SCHEMA infrastructure TO anon, authenticated;
GRANT USAGE ON SCHEMA demand TO anon, authenticated;
GRANT USAGE ON SCHEMA indices TO anon, authenticated;

-- Grant SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA core TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA infrastructure TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA demand TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA indices TO anon, authenticated;

-- Auto-grant SELECT on future tables in these schemas
ALTER DEFAULT PRIVILEGES IN SCHEMA core
  GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA infrastructure
  GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA demand
  GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA indices
  GRANT SELECT ON TABLES TO anon, authenticated;


-- =============================================================================
-- END OF DDL
-- =============================================================================
-- If you reached this line without errors — the database is ready.
-- Expected result in Supabase: "Success. No rows returned."
-- 
-- Next step: expose the four custom schemas via Supabase UI:
--   Settings → Data API → Exposed schemas → add: core, infrastructure, demand, indices
--
-- Then: verify via Table Editor — you should see 6 tables across 4 schemas:
--   core.regions
--   infrastructure.substations
--   infrastructure.powerlines
--   infrastructure.power_plants
--   demand.announcements
--   indices.methodology_versions
--   indices.grid_feasibility
-- =============================================================================


-- -----------------------------------------------------------------------------
-- ROLLBACK (commented out — uncomment and run only if you need to start over)
-- -----------------------------------------------------------------------------
-- DROP SCHEMA IF EXISTS indices CASCADE;
-- DROP SCHEMA IF EXISTS demand CASCADE;
-- DROP SCHEMA IF EXISTS infrastructure CASCADE;
-- DROP SCHEMA IF EXISTS core CASCADE;
