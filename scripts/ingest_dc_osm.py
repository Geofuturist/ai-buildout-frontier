#!/usr/bin/env python3
"""
ingest_dc_osm.py — Ingest OpenStreetMap datacenters GeoJSON into Supabase.

Usage:
    python scripts/ingest_dc_osm.py <path_to_geojson> <snapshot_date>

Example:
    python scripts/ingest_dc_osm.py data/USA_Datacenters_point.geojson 2026-04-01

Idempotent: ON CONFLICT (source, source_id) DO UPDATE — safe to re-run.
All credentials read from .env (DATABASE_URL or SUPABASE_DB_* vars).
"""

import argparse
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
# Property name mapping — OSM column → table column
# OSM GeoJSON from Overpass/QuickOSM exports have truncated column names.
# ---------------------------------------------------------------------------
OSM_NAME_COL = "name"
OSM_OPERATOR_COL = "operator"
OSM_FULL_ID_COL = "full_id"    # e.g. 'r2744301', 'w456789', 'n123'
OSM_OSM_TYPE_COL = "osm_type"  # 'relation', 'way', 'node'
OSM_OSM_ID_COL = "osm_id"     # bare numeric string


def build_source_id(row: dict) -> str:
    """
    Construct OSM source_id in canonical 'type/id' format.
    e.g. osm_type='way', osm_id='123456' → 'way/123456'
    Falls back to full_id if split fields are absent.
    """
    osm_type = row.get(OSM_OSM_TYPE_COL)
    osm_id = row.get(OSM_OSM_ID_COL)
    if osm_type and osm_id:
        return f"{osm_type}/{osm_id}"
    full_id = row.get(OSM_FULL_ID_COL)
    if full_id:
        return str(full_id)
    raise ValueError(f"Cannot derive source_id from row: {row}")


def build_raw_tags(props: dict) -> dict:
    """
    Return full properties dict as raw_tags JSONB.
    Converts non-serialisable types (Timestamp, NaT, NaN) to None/str.
    """
    cleaned: dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            cleaned[k] = None
        elif hasattr(v, "isoformat"):          # datetime / Timestamp
            cleaned[k] = v.isoformat()
        elif isinstance(v, float) and v != v:  # NaN check
            cleaned[k] = None
        else:
            cleaned[k] = v
    return cleaned


def get_db_connection() -> psycopg2.extensions.connection:
    """
    Connect to Postgres. Reads DATABASE_URL first; falls back to
    individual SUPABASE_DB_* environment variables.
    """
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    host = os.environ["SUPABASE_DB_HOST"]
    port = os.environ.get("SUPABASE_DB_PORT", "5432")
    dbname = os.environ.get("SUPABASE_DB_NAME", "postgres")
    user = os.environ["SUPABASE_DB_USER"]
    password = os.environ["SUPABASE_DB_PASSWORD"]
    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )


INSERT_SQL = """
INSERT INTO infrastructure.datacenters_osm
  (source, source_id, name, operator, geometry, raw_tags, source_version, license)
VALUES
  (%(source)s, %(source_id)s, %(name)s, %(operator)s,
   ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326),
   %(raw_tags)s::jsonb, %(source_version)s, %(license)s)
ON CONFLICT (source, source_id) DO UPDATE SET
  name           = EXCLUDED.name,
  operator       = EXCLUDED.operator,
  geometry       = EXCLUDED.geometry,
  raw_tags       = EXCLUDED.raw_tags,
  source_version = EXCLUDED.source_version,
  ingested_at    = NOW();
"""


def ingest(geojson_path: Path, snapshot_date: date) -> None:
    log.info("Reading GeoJSON: %s", geojson_path)
    gdf = gpd.read_file(geojson_path)
    log.info("Loaded %d features", len(gdf))

    # Ensure CRS is WGS84
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    # All features must have geometry in this dataset
    null_geom = gdf.geometry.isna().sum()
    if null_geom > 0:
        log.warning("%d features have NULL geometry — skipping them", null_geom)
        gdf = gdf[gdf.geometry.notna()].copy()

    conn = get_db_connection()
    log.info("Connected to database")

    inserted = 0
    skipped = 0

    try:
        with conn:  # transaction: commit on success, rollback on any exception
            with conn.cursor() as cur:
                psycopg2.extras.register_uuid()

                for i, row in gdf.iterrows():
                    props = {
                        k: v for k, v in row.items() if k != "geometry"
                    }

                    try:
                        source_id = build_source_id(props)
                    except ValueError as exc:
                        log.warning("Row %d: %s — skipping", i, exc)
                        skipped += 1
                        continue

                    geom = row.geometry
                    geom_geojson = json.dumps(mapping(geom))

                    record = {
                        "source": "openstreetmap",
                        "source_id": source_id,
                        "name": props.get(OSM_NAME_COL) or None,
                        "operator": props.get(OSM_OPERATOR_COL) or None,
                        "geometry": geom_geojson,
                        "raw_tags": json.dumps(build_raw_tags(props)),
                        "source_version": snapshot_date,
                        "license": "ODbL",
                    }
                    cur.execute(INSERT_SQL, record)
                    inserted += 1

                    if inserted % 100 == 0:
                        log.info("  Processed %d / %d ...", inserted, len(gdf))

        log.info("✅ Done. Inserted/updated: %d | Skipped: %d", inserted, skipped)

    except Exception:
        log.exception("❌ Transaction rolled back due to error")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest OSM datacenters GeoJSON into Supabase."
    )
    parser.add_argument("geojson", type=Path, help="Path to GeoJSON file")
    parser.add_argument(
        "snapshot_date",
        type=date.fromisoformat,
        help="OSM snapshot date (YYYY-MM-DD), e.g. 2026-04-01",
    )
    args = parser.parse_args()

    if not args.geojson.exists():
        log.error("File not found: %s", args.geojson)
        sys.exit(1)

    ingest(args.geojson, args.snapshot_date)


if __name__ == "__main__":
    main()
