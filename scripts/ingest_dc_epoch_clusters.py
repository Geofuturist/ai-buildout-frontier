#!/usr/bin/env python3
"""
ingest_dc_epoch_clusters.py — Ingest Epoch AI GPU Clusters GeoJSON into Supabase.

Usage:
    python scripts/ingest_dc_epoch_clusters.py <path_to_geojson> [--source-version YYYY-MM-DD]

Example:
    python scripts/ingest_dc_epoch_clusters.py data/epoch_gpu_clusters_2026_05_04.geojson

Defaults source_version to 2026-05-04 (encoded in filename); override via CLI.
Idempotent: ON CONFLICT (source, source_id, source_version) DO UPDATE — safe to re-run.

Property name mapping (verified against real 2026-05-04 snapshot):
    'Name'                → name
    'Owner'               → owner
    'Country'             → country
    'Status'              → status   (normalized via STATUS_MAPPING)
    'Certainty'           → certainty
    'Power Capacity (MW)' → power_capacity_mw
    'H100 equivalents'    → h100_equivalent
    'Max OP/s'            → ops_total
    geometry              → geometry  (NULL for 188 non-spatial records)
    full properties       → raw_attributes
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
COL_STATUS = "Status"
COL_CERTAINTY = "Certainty"
COL_POWER_MW = "Power Capacity (MW)"
COL_H100 = "H100 equivalents"
COL_OPS = "Max OP/s"
COL_CITATION = "citation"  # pre-processed metadata field

DEFAULT_SOURCE_VERSION = date(2026, 5, 4)

# ---------------------------------------------------------------------------
# Status normalization
# All keys are lowercase-stripped — normalize input before lookup.
# ---------------------------------------------------------------------------
STATUS_MAPPING: dict[str, str] = {
    "operational": "operational",
    "in operation": "operational",
    "active": "operational",
    "existing": "operational",      # Epoch clusters 2026-05-04 uses 'Existing'
    "under construction": "under_construction",
    "construction": "under_construction",
    "planned": "planned",
    "in planning": "planned",
    "announced": "announced",
    "decommissioned": "decommissioned",
    "retired": "decommissioned",
    # fallback: 'unknown'
}


def normalize_status(raw: Optional[str]) -> str:
    """Map raw Epoch status string to dc_status enum value."""
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


def derive_source_id(name: Optional[str], owner: Optional[str], country: Optional[str],
                     h100: Optional[float], power: Optional[float],
                     row_idx: int) -> str:
    parts = [
        (name or "").strip(),
        (owner or "").strip(),
        (country or "").strip(),
        str(round(h100, 4)) if h100 is not None else "",
        str(round(power, 4)) if power is not None else "",
        str(row_idx),
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def clean_value(v: Any) -> Any:
    """Convert non-JSON-serialisable types (NaT, NaN, Timestamp) to None/str."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def build_raw_attributes(props: dict) -> dict:
    """Return cleaned full properties dict for raw_attributes JSONB."""
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
INSERT INTO infrastructure.datacenters_epoch_clusters
  (source, source_id, name, owner, country, status, certainty,
   power_capacity_mw, h100_equivalent, ops_total,
   geometry, geocoding_precision, citation,
   raw_attributes, source_version, license)
VALUES
  (%(source)s, %(source_id)s, %(name)s, %(owner)s, %(country)s,
   %(status)s::infrastructure.dc_status,
   %(certainty)s,
   %(power_capacity_mw)s, %(h100_equivalent)s, %(ops_total)s,
   CASE WHEN %(geometry)s::text IS NULL
        THEN NULL
        ELSE ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326)
   END,
   %(geocoding_precision)s::infrastructure.geocoding_precision,
   %(citation)s,
   %(raw_attributes)s::jsonb,
   %(source_version)s, %(license)s)
ON CONFLICT (source, source_id, source_version) DO UPDATE SET
  name               = EXCLUDED.name,
  owner              = EXCLUDED.owner,
  country            = EXCLUDED.country,
  status             = EXCLUDED.status,
  certainty          = EXCLUDED.certainty,
  power_capacity_mw  = EXCLUDED.power_capacity_mw,
  h100_equivalent    = EXCLUDED.h100_equivalent,
  ops_total          = EXCLUDED.ops_total,
  geometry           = EXCLUDED.geometry,
  geocoding_precision = EXCLUDED.geocoding_precision,
  citation           = EXCLUDED.citation,
  raw_attributes     = EXCLUDED.raw_attributes,
  ingested_at        = NOW();
"""


def ingest(geojson_path: Path, source_version: date) -> None:
    log.info("Reading GeoJSON: %s", geojson_path)
    gdf = gpd.read_file(geojson_path)
    log.info("Loaded %d features (expected 786)", len(gdf))

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    spatial_count = gdf.geometry.notna().sum()
    non_spatial_count = gdf.geometry.isna().sum()
    log.info("  Spatial (has geometry): %d", spatial_count)
    log.info("  Non-spatial (NULL geometry): %d", non_spatial_count)

    conn = get_db_connection()
    log.info("Connected to database")

    inserted = 0
    updated = 0

    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.register_uuid()

                for i, row in gdf.iterrows():
                    props = {k: v for k, v in row.items() if k != "geometry"}

                    name = props.get(COL_NAME)
                    owner = props.get(COL_OWNER)
                    country = props.get(COL_COUNTRY)

                    source_id = derive_source_id(
                        name if not _is_na(name) else None,
                        owner if not _is_na(owner) else None,
                        country if not _is_na(country) else None,
                        _to_float(props.get(COL_H100)),
                        _to_float(props.get(COL_POWER_MW)),
                        i,
                    )

                    geom = row.geometry
                    geom_geojson: Optional[str] = (
                        json.dumps(mapping(geom)) if geom is not None else None
                    )

                    power = _to_float(props.get(COL_POWER_MW))
                    h100 = _to_float(props.get(COL_H100))
                    ops = _to_float(props.get(COL_OPS))

                    record = {
                        "source": "epoch_ai_gpu_clusters",
                        "source_id": source_id,
                        "name": _str_or_none(name),
                        "owner": _str_or_none(owner),
                        "country": _str_or_none(country),
                        "status": normalize_status(_str_or_none(props.get(COL_STATUS))),
                        "certainty": _str_or_none(props.get(COL_CERTAINTY)),
                        "power_capacity_mw": power,
                        "h100_equivalent": h100,
                        "ops_total": ops,
                        "geometry": geom_geojson,
                        "geocoding_precision": None,  # not in 2026-05-04 snapshot
                        "citation": _str_or_none(props.get(COL_CITATION)),
                        "raw_attributes": json.dumps(build_raw_attributes(props)),
                        "source_version": source_version,
                        "license": "CC-BY-4.0",
                    }

                    cur.execute(INSERT_SQL, record)
                    inserted += 1

                    if inserted % 100 == 0:
                        log.info("  Processed %d / %d ...", inserted, len(gdf))

        log.info("✅ Done. Inserted/updated: %d records", inserted)
        log.info("   Run verification query:")
        log.info(
            "   SELECT COUNT(*), has_geometry FROM "
            "infrastructure.datacenters_epoch_clusters "
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
    """Return True if value is None, NaN, or pandas NA."""
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
        description="Ingest Epoch AI GPU Clusters GeoJSON into Supabase."
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
