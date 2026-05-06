-- =============================================================================
-- Migration: A3_01_datacenter_layers.sql
-- Phase: A3.1 — Datacenter Layers Backend
-- Author: [CODE] AI Buildout Frontier (Sonnet)
-- SPEC: SPEC_VA_A3_DATACENTER_LAYERS_BACKEND.md
-- Idempotent: yes — safe to re-run, no-op if already applied
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------------

-- infrastructure.geocoding_precision
DO $$ BEGIN
  CREATE TYPE infrastructure.geocoding_precision AS ENUM (
    'street_level',
    'city',
    'region',
    'country_centroid'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- infrastructure.dc_status
DO $$ BEGIN
  CREATE TYPE infrastructure.dc_status AS ENUM (
    'operational',
    'under_construction',
    'planned',
    'announced',
    'decommissioned',
    'unknown'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- LAYER 1: infrastructure.datacenters_osm
-- Source: OpenStreetMap snapshot (ODbL)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS infrastructure.datacenters_osm (
  id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
  source           TEXT        NOT NULL DEFAULT 'openstreetmap',
  source_id        TEXT        NOT NULL,            -- e.g. 'way/123456', 'node/789'
  name             TEXT,
  operator         TEXT,
  geometry         GEOMETRY(Point, 4326) NOT NULL,
  raw_tags         JSONB,                           -- full OSM property dictionary
  source_version   DATE        NOT NULL,            -- date of OSM snapshot
  license          TEXT        NOT NULL DEFAULT 'ODbL',
  ingested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT datacenters_osm_source_id_unique UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_osm_geometry
  ON infrastructure.datacenters_osm USING GIST (geometry);

-- ---------------------------------------------------------------------------
-- LAYER 2: infrastructure.datacenters_epoch_clusters
-- Source: Epoch AI GPU Clusters (CC-BY-4.0)
-- Note: geocoding_precision is nullable — Epoch 2026-05-04 snapshot does not
-- publish this field. CHECK constraint intentionally omitted (ARCH decision
-- 2026-05-05). Frontend handles NULL as "precision unspecified".
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS infrastructure.datacenters_epoch_clusters (
  id                   UUID      PRIMARY KEY DEFAULT uuid_generate_v4(),
  source               TEXT      NOT NULL DEFAULT 'epoch_ai_gpu_clusters',
  source_id            TEXT      NOT NULL,          -- SHA-256(name|owner|country)[:16]
  name                 TEXT,
  owner                TEXT,
  country              TEXT,
  status               infrastructure.dc_status NOT NULL DEFAULT 'unknown',
  certainty            TEXT,                        -- Epoch certainty: 'Confirmed', 'Likely', 'Unlikely'
  power_capacity_mw    NUMERIC,
  h100_equivalent      NUMERIC,
  ops_total            NUMERIC,                     -- Max OP/s; can be very large
  geometry             GEOMETRY(Point, 4326),       -- nullable: 188 records without geometry
  has_geometry         BOOLEAN GENERATED ALWAYS AS (geometry IS NOT NULL) STORED,
  geocoding_precision  infrastructure.geocoding_precision,  -- nullable: not in 2026-05-04 snapshot
  -- TODO: Epoch GPU Clusters dataset on 2026-05-04 does not include
  -- geocoding_precision field. When Epoch starts publishing it,
  -- backfill via separate migration. Frontend handles NULL as
  -- "precision unspecified" with default opacity.
  citation             TEXT,
  raw_attributes       JSONB,                       -- full original Epoch row preserved
  source_version       DATE      NOT NULL,
  license              TEXT      NOT NULL DEFAULT 'CC-BY-4.0',
  ingested_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT datacenters_clusters_source_unique UNIQUE (source, source_id, source_version)
);

CREATE INDEX IF NOT EXISTS idx_dc_clusters_geometry
  ON infrastructure.datacenters_epoch_clusters USING GIST (geometry)
  WHERE geometry IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dc_clusters_status
  ON infrastructure.datacenters_epoch_clusters (status);

CREATE INDEX IF NOT EXISTS idx_dc_clusters_has_geometry
  ON infrastructure.datacenters_epoch_clusters (has_geometry);

-- ---------------------------------------------------------------------------
-- LAYER 3: infrastructure.datacenters_epoch_frontier
-- Source: Epoch AI Frontier Data Centers (CC-BY-4.0)
-- Note: geometry is nullable — Epoch dataset as of 2026-05-04 contains 38
-- records, 5 of which lack coordinates (ARCH decision 2026-05-05: ingest all,
-- do not block on missing geometry). has_geometry generated column mirrors
-- Clusters table pattern.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS infrastructure.datacenters_epoch_frontier (
  id                   UUID      PRIMARY KEY DEFAULT uuid_generate_v4(),
  source               TEXT      NOT NULL DEFAULT 'epoch_ai_frontier',
  source_id            TEXT      NOT NULL,          -- SHA-256(name|owner|country)[:16]
  name                 TEXT,
  owner                TEXT,
  country              TEXT,
  status               infrastructure.dc_status NOT NULL DEFAULT 'unknown',
  power_capacity_mw    NUMERIC,
  h100_equivalent      NUMERIC,
  ops_total            NUMERIC,
  build_start          DATE,
  expected_operational DATE,
  geometry             GEOMETRY(Point, 4326),       -- nullable: 5 records without coords
  has_geometry         BOOLEAN GENERATED ALWAYS AS (geometry IS NOT NULL) STORED,
  citation             TEXT,
  raw_attributes       JSONB,
  source_version       DATE      NOT NULL,
  license              TEXT      NOT NULL DEFAULT 'CC-BY-4.0',
  ingested_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT datacenters_frontier_source_unique UNIQUE (source, source_id, source_version)
);

CREATE INDEX IF NOT EXISTS idx_dc_frontier_geometry
  ON infrastructure.datacenters_epoch_frontier USING GIST (geometry)
  WHERE geometry IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dc_frontier_status
  ON infrastructure.datacenters_epoch_frontier (status);

-- =============================================================================
-- End of migration A3_01_datacenter_layers.sql
-- =============================================================================
