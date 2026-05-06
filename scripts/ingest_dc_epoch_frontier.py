#!/usr/bin/env python3
"""
ingest_dc_epoch_frontier.py — Ingest Epoch AI Frontier Data Centers GeoJSON into Supabase.

Usage:
    python scripts/ingest_dc_epoch_frontier.py <path_to_geojson> [--source-version YYYY-MM-DD]

Example:
    python scripts/ingest_dc_epoch_frontier.py data/epoch_frontier_datacenters_2026_05_04.geojson

Defaults source_version to 2026-05-04. Override via CLI.
Idempotent: ON CONFLICT (source, source_id, source_version) DO UPDATE — safe to re-run.

Property name mapping (verified against real 2026-05-04 snapshot, 38 records):
    'Name'                                → name
    'Owner'                               → owner
    'Country'                             → country
    (no status column in this snapshot)   → status = 'unknown' (DEFAULT)
    'Current power (MW)'                  → power_capacity_mw
    'Current H100 equivalents'            → h100_equivalent
    (no ops_total in this snapshot)       → ops_total = NULL
    (no build_start in this snapshot)     → build_start = NULL
    (no expected_operational in snapshot) → expected_operational = NULL
    'citation'                            → citation
    geometry                              → geometry (NULL for 5 of 38 records)
    full properties                       → raw_attributes

ARCH decision 2026-05-05: geometry is nullable for Frontier table (parity with Clusters).
All 38 records are ingested; 5 without coordinates get geometry=NULL, has_geometry=false.
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os
from shapely.geometry import mapping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column names — verified against real 2026-05-04 snapshot.
# Single place to update if Epoch renames columns in a future release.
# ---------------------------------------------------------------------------
COL_NAME = "Name"
COL_OWNER = "Owner"
COL_COUNTRY = "Country"
COL_POWER_MW = "Current power (MW)"
COL_H100 = "Current H100 equivalents"
COL_CITATION = "citation"  # pre-processed metadata field already in file

# Fields not present in 2026-05-04 snapshot — kept here for future use:
COL_STATUS = None            # not in file; all records get DEFAULT 'unknown'
COL_OPS_TOTAL = None         # not in file; all records get NULL
COL_BUILD_START = None       # not in file
COL_EXPECTED_OPERATIONAL = None  # not in file

DEFAULT_SOURCE_VERSION = date(2026, 5, 4)

# Status mapping kept here for when Epoch adds a status column.
# 'existing' → 'operational' confirmed (ARCH 2026-05-05).
STATUS_MAPPING: dict[str, str] = {
    "operational": "operational",
    "in operation": "operational",
    "active": "operational",
    "existing": "operational",
    "under construction": "under_construction",
    "construction": "under_construction",
    "planned": "planned",
    "in planning": "planned",
    "announced": "announced",
    "decommissioned": "decommissioned",
    "retired": "decommissioned",
}


def normalize_status(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    normalized = raw.strip().lower()
    result = STATUS_MAPPING.get(normalized)
    if result is None:
        log.warning(
            "Unrecognised status value '%s' — defaulting to 'unknown'. "
            "Add to STATUS_MAPPING if this is a valid Epoch value.",
            raw,
        )
        return "unknown"
    return result


def derive_source_id(name: Optional[str], owner: Optional[str], country: Optional[str]) -> str:
    """
    Deterministic source_id: SHA-256 of 'name|owner|country' (None → '').
    First 16 hex chars. Provides idempotency via ON CONFLICT even without
    an Epoch-native stable ID. If Epoch adds their own ID field in future,
    switch to that and backfill via migration.
    """
    parts = [
        (name or "").strip(),
        (owner or "").strip(),
        (country or "").strip(),
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def clean_value(v: Any) -> Any:
    """Convert non-JSON-serialisable types to None/str."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float) and v != v:
        return None
    return v


def build_raw_attributes(props: dict) -> dict:
    return {k: clean_value(v) for k, v in props.items()}


def get_db_connection() -> psycopg2.extensions.connection:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=os.environ.get("SUPABASE_DB_PORT", "5432"),
        dbname=os.environ.get("SUPABASE_DB_NAME", "postgres"),
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
    )


INSERT_SQL = """
INSERT INTO infrastructure.datacenters_epoch_frontier
  (source, source_id, name, owner, country, status,
   power_capacity_mw, h100_equivalent, ops_total,
   build_start, expected_operational,
   geometry, citation, raw_attributes, source_version, license)
VALUES
  (%(source)s, %(source_id)s, %(name)s, %(owner)s, %(country)s,
   %(status)s::infrastructure.dc_status,
   %(power_capacity_mw)s, %(h100_equivalent)s, %(ops_total)s,
   %(build_start)s, %(expected_operational)s,
   CASE WHEN %(geometry)s::text IS NULL
        THEN NULL
        ELSE ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326)
   END,
   %(citation)s, %(raw_attributes)s::jsonb,
   %(source_version)s, %(license)s)
ON CONFLICT (source, source_id, source_version) DO UPDATE SET
  name                 = EXCLUDED.name,
  owner                = EXCLUDED.owner,
  country              = EXCLUDED.country,
  status               = EXCLUDED.status,
  power_capacity_mw    = EXCLUDED.power_capacity_mw,
  h100_equivalent      = EXCLUDED.h100_equivalent,
  ops_total            = EXCLUDED.ops_total,
  build_start          = EXCLUDED.build_start,
  expected_operational = EXCLUDED.expected_operational,
  geometry             = EXCLUDED.geometry,
  citation             = EXCLUDED.citation,
  raw_attributes       = EXCLUDED.raw_attributes,
  ingested_at          = NOW();
"""


def ingest(geojson_path: Path, source_version: date) -> None:
    log.info("Reading GeoJSON: %s", geojson_path)
    gdf = gpd.read_file(geojson_path)
    total = len(gdf)
    log.info("Loaded %d features (SPEC expected 23; dataset now has %d)", 23, total)

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    spatial_count = gdf.geometry.notna().sum()
    non_spatial_count = gdf.geometry.isna().sum()
    log.info("  With geometry: %d", spatial_count)
    log.info("  Without geometry (will be ingested with geometry=NULL): %d", non_spatial_count)

    if non_spatial_count > 0:
        log.info(
            "  NOTE: %d records lack coordinates — ingesting with geometry=NULL "
            "(ARCH decision 2026-05-05). [RES] is aware.",
            non_spatial_count,
        )

    conn = get_db_connection()
    log.info("Connected to database")

    inserted = 0

    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.register_uuid()

                for i, row in gdf.iterrows():
                    props = {k: v for k, v in row.items() if k != "geometry"}

                    name = _str_or_none(props.get(COL_NAME))
                    owner = _str_or_none(props.get(COL_OWNER))
                    country = _str_or_none(props.get(COL_COUNTRY))

                    source_id = derive_source_id(name, owner, country)

                    geom = row.geometry
                    geom_geojson: Optional[str] = (
                        json.dumps(mapping(geom)) if geom is not None else None
                    )

                    record = {
                        "source": "epoch_ai_frontier",
                        "source_id": source_id,
                        "name": name,
                        "owner": owner,
                        "country": country,
                        "status": "unknown",   # column absent in 2026-05-04 snapshot
                        "power_capacity_mw": _to_float(props.get(COL_POWER_MW)),
                        "h100_equivalent": _to_float(props.get(COL_H100)),
                        "ops_total": None,     # column absent in 2026-05-04 snapshot
                        "build_start": None,   # column absent in 2026-05-04 snapshot
                        "expected_operational": None,  # column absent in snapshot
                        "geometry": geom_geojson,
                        "citation": _str_or_none(props.get(COL_CITATION)),
                        "raw_attributes": json.dumps(build_raw_attributes(props)),
                        "source_version": source_version,
                        "license": "CC-BY-4.0",
                    }

                    cur.execute(INSERT_SQL, record)
                    inserted += 1

                    if inserted % 10 == 0:
                        log.info("  Processed %d / %d ...", inserted, total)

        log.info("✅ Done. Inserted/updated: %d / %d records", inserted, total)
        log.info("   Run verification query:")
        log.info(
            "   SELECT COUNT(*), has_geometry FROM "
            "infrastructure.datacenters_epoch_frontier "
            "GROUP BY has_geometry;"
        )

    except Exception:
        log.exception("❌ Transaction rolled back due to error")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_na(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    try:
        import pandas as pd
        return pd.isna(v)
    except Exception:
        return False


def _str_or_none(v: Any) -> Optional[str]:
    if _is_na(v):
        return None
    s = str(v).strip()
    return s if s else None


def _to_float(v: Any) -> Optional[float]:
    if _is_na(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Epoch AI Frontier Data Centers GeoJSON into Supabase."
    )
    parser.add_argument("geojson", type=Path, help="Path to GeoJSON file")
    parser.add_argument(
        "--source-version",
        type=date.fromisoformat,
        default=DEFAULT_SOURCE_VERSION,
        help="Source version date (YYYY-MM-DD). Default: 2026-05-04",
    )
    args = parser.parse_args()

    if not args.geojson.exists():
        log.error("File not found: %s", args.geojson)
        sys.exit(1)

    ingest(args.geojson, args.source_version)


if __name__ == "__main__":
    main()
