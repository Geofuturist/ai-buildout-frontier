"""
Virginia Grid Feasibility Index — ingestion script.

Reads va_grid_feasibility_index.geojson and loads:
- 133 county boundaries into core.regions (UPSERT)
- 133 feasibility scores into indices.grid_feasibility (INSERT)

Usage:
    python ingest_va_feasibility.py [path/to/geojson]

Environment:
    DATABASE_URL — Postgres connection string (Session Pooler from Supabase)

Setup:
    pip install psycopg2-binary python-dotenv
    Create .env in the same folder as this script with DATABASE_URL set.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
import os


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION = "v1.0"
COUNTRY_CODE = "US"
ADMIN_LEVEL = 2  # County level
DEFAULT_GEOJSON_PATH = r"D:\GISData\Energy\USA\va_grid_feasibility_index.geojson"
EXPECTED_FEATURE_COUNT = 133

# Fields to ignore from GeoJSON properties (presentation layer only)
IGNORED_FIELDS = {"feasibility_color", "feasibility_label", "popup_text"}


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    """Configure logging to stdout with a readable timestamp format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# GeoJSON loading
# ---------------------------------------------------------------------------


def load_geojson(path: Path) -> dict[str, Any]:
    """Load and basic-validate GeoJSON file.

    Args:
        path: Path to the GeoJSON file.

    Returns:
        Parsed GeoJSON dict.

    Raises:
        SystemExit: If the file is missing or is not a valid FeatureCollection.
    """
    if not path.exists():
        logging.error("GeoJSON file not found: %s", path)
        sys.exit(1)

    logging.info("Loading GeoJSON: %s", path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        logging.error("Expected a FeatureCollection, got: %s", data.get("type"))
        sys.exit(1)

    features = data.get("features", [])
    count = len(features)
    status = "✓" if count == EXPECTED_FEATURE_COUNT else "✗ (expected %d)" % EXPECTED_FEATURE_COUNT
    logging.info("Found %d features (expected: %d) %s", count, EXPECTED_FEATURE_COUNT, status)

    if count == 0:
        logging.error("GeoJSON contains no features. Aborting.")
        sys.exit(1)

    return data


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_connection() -> "psycopg2.connection":
    """Create and return a database connection.

    Reads DATABASE_URL from environment (loaded from .env).

    Raises:
        SystemExit: If DATABASE_URL is missing or connection fails.
    """
    # Load .env from the directory containing this script
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.error(
            "DATABASE_URL not found. Create a .env file next to this script with:\n"
            "  DATABASE_URL=postgresql://postgres.xxxxx:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
        )
        sys.exit(1)

    logging.info("Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except psycopg2.OperationalError as exc:
        logging.error("Failed to connect to database: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core ingestion functions
# ---------------------------------------------------------------------------


def upsert_region(cur: Any, feature: dict[str, Any]) -> str:
    """UPSERT a county boundary into core.regions.

    Args:
        cur: psycopg2 cursor.
        feature: A single GeoJSON feature dict.

    Returns:
        The uuid (as str) of the upserted region row.
    """
    props = feature["properties"]
    geometry_json = json.dumps(feature["geometry"])

    cur.execute(
        """
        INSERT INTO core.regions (name, country_code, admin_level, admin_code, geometry)
        VALUES (%(name)s, %(country_code)s, %(admin_level)s, %(admin_code)s,
                ST_GeomFromGeoJSON(%(geometry)s))
        ON CONFLICT (country_code, admin_level, admin_code)
        DO UPDATE SET
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            updated_at = now()
        RETURNING id;
        """,
        {
            "name": props["county_name"],
            "country_code": COUNTRY_CODE,
            "admin_level": ADMIN_LEVEL,
            "admin_code": props["fips"],
            "geometry": geometry_json,
        },
    )
    row = cur.fetchone()
    return str(row[0])


def build_components(props: dict[str, Any]) -> dict[str, Any]:
    """Build the components JSONB dict from feature properties.

    Args:
        props: The properties dict of a GeoJSON feature.

    Returns:
        Structured dict matching the schema defined in ARCHITECTURE_DECISIONS §6.2.
    """
    return {
        "is_dc_hotspot": bool(props["is_dc_hotspot"]),
        "headroom": {
            "headroom_mw": float(props["headroom_mw"]),
            "summer_cap_mw": float(props["summer_cap_mw"]),
            "net_gen_mwh": float(props["net_gen_mwh"]),
            "peak_demand_mw": float(props["peak_demand_mw"]),
        },
        "queue": {
            "q_projects": int(props["q_projects"]),
            "q_total_mw": float(props["q_total_mw"]),
            "q_realistic_mw": float(props["q_realistic_mw"]),
            "q_solar_mw": float(props["q_solar_mw"]),
            "q_battery_mw": float(props["q_battery_mw"]),
            "q_wind_mw": float(props["q_wind_mw"]),
            "q_gas_mw": float(props["q_gas_mw"]),
            "completion_rate_pct": float(props["completion_rate_pct"]),
        },
        "substations": {
            "sub_critical": int(props["sub_critical"]),
            "sub_high": int(props["sub_high"]),
            "sub_throughput": int(props["sub_throughput"]),
        },
        "feasibility_score": int(props["feasibility_score"]),
    }


def insert_feasibility(
    cur: Any,
    region_id: str,
    feature: dict[str, Any],
    computed_at: datetime,
) -> None:
    """INSERT a feasibility record into indices.grid_feasibility.

    Each run creates a new snapshot row (INSERT-only, by design).
    See ARCHITECTURE_DECISIONS §4.3.

    Args:
        cur: psycopg2 cursor.
        region_id: UUID of the parent region in core.regions.
        feature: A single GeoJSON feature dict.
        computed_at: Shared timestamp for this entire ingestion run.
    """
    props = feature["properties"]
    components = build_components(props)

    cur.execute(
        """
        INSERT INTO indices.grid_feasibility
            (region_id, methodology_version, computed_at, value, category, components)
        VALUES
            (%(region_id)s, %(methodology_version)s, %(computed_at)s,
             %(value)s, %(category)s, %(components)s);
        """,
        {
            "region_id": region_id,
            "methodology_version": METHODOLOGY_VERSION,
            "computed_at": computed_at,
            "value": float(props["feasibility_ratio"]),
            "category": props["feasibility_category"],
            "components": Json(components),
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest Virginia Grid Feasibility Index GeoJSON into Supabase."
    )
    parser.add_argument(
        "geojson_path",
        nargs="?",
        default=DEFAULT_GEOJSON_PATH,
        help="Path to va_grid_feasibility_index.geojson (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point. Returns exit code (0 = success, 1 = error)."""
    setup_logging()
    args = parse_args()
    geojson_path = Path(args.geojson_path)

    # 1. Load GeoJSON
    data = load_geojson(geojson_path)
    features = data["features"]

    # 2. Connect to database
    conn = get_connection()

    # 3. One shared timestamp for this entire ingestion snapshot
    computed_at = datetime.now(tz=timezone.utc)
    logging.info("Starting ingestion at %s", computed_at.strftime("%Y-%m-%d %H:%M:%S UTC"))

    # 4. Category counters for summary
    category_counts: dict[str, int] = {}

    try:
        with conn:  # Transaction: commit on success, rollback on exception
            with conn.cursor() as cur:
                for idx, feature in enumerate(features, start=1):
                    props = feature["properties"]
                    fips = props["fips"]
                    name = props["county_name"]
                    ratio = props["feasibility_ratio"]
                    category = props["feasibility_category"]

                    try:
                        region_id = upsert_region(cur, feature)
                        insert_feasibility(cur, region_id, feature, computed_at)
                    except (psycopg2.Error, KeyError, ValueError) as exc:
                        logging.error(
                            "[%3d/%d] FAILED — %s (FIPS %s): %s",
                            idx,
                            len(features),
                            name,
                            fips,
                            exc,
                        )
                        raise  # Triggers rollback via context manager

                    category_counts[category] = category_counts.get(category, 0) + 1

                    logging.info(
                        "[%3d/%d] %-20s (FIPS %s) → region upserted, feasibility=%.3f (%s)",
                        idx,
                        len(features),
                        name,
                        fips,
                        ratio,
                        category,
                    )

        # 5. Success summary
        logging.info("Committing transaction...")
        logging.info(
            "✓ Success: %d regions upserted, %d feasibility records inserted",
            len(features),
            len(features),
        )
        category_summary = ", ".join(
            f"{cat}={cnt}" for cat, cnt in sorted(category_counts.items())
        )
        logging.info("Categories: %s", category_summary)
        return 0

    except Exception as exc:  # noqa: BLE001
        logging.error("Ingestion failed, transaction rolled back: %s", exc)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
