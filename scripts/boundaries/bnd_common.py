"""
bnd_common.py -- shared helpers for the abf-boundaries-v0.1.0 pipeline.

Helper module only -- not runnable directly. Imported by:
  fetch_boundary_sources.py, build_boundaries.py, validate_boundaries.py,
  make_registry_template.py

Spec: SPEC_BND_boundaries_v0_1.md (2nd revision, 2026-09-27).
All topology operations happen in EPSG:4326 (explicit reprojection from
source CRSs). All areas and tolerances are computed in EPSG:6933 (world
equal-area). A fixed precision grid + make_valid is applied before and
after every boolean geometry operation, per SPEC/ADR v6.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# --------------------------------------------------------------------------
# Constants (SPEC references in comments)
# --------------------------------------------------------------------------

NE_VERSION = "v5.1.2"
NE_BASE_URL = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{NE_VERSION}/geojson/"
GEOBOUNDARIES_META_URL = (
    "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/"
    "releaseData/geoBoundariesOpen-meta.csv"
)

CRS_WGS84 = "EPSG:4326"
CRS_EQUAL_AREA = "EPSG:6933"  # world equal-area, for areas and tolerances (SPEC S4)

PRECISION_GRID = 1e-7  # degrees -- shapely.set_precision grid (SPEC S4)
BOUNDARY_TOUCH_TOL_DEG = 1e-6  # degrees -- "touches neighbour" test (SPEC S4.5 step 3)

OVERLAP_TOL_KM2 = 0.01  # validation check 1 (SPEC S5), per pair
HOLE_WHITELIST_TOL_KM2 = 0.01  # validation check 2 (SPEC S5)
CONFORM_RESIDUAL_TOL_KM2 = 0.05  # validation check 3 (SPEC S5), per country
NESTING_MIN_FRACTION = 0.999  # validation check 4 (SPEC S5)
WATER_GAP_FRACTION = 0.50  # amendment 2 (ARCH_to_CODE_BND_go_v0_1.md): gap part is
                            # "water" if >=50% of its area lies inside ne_10m_lakes

ADM0_EXPECTED_UNITS = 242  # SPEC S4.1 p.4

# France: NE `region` name -> INSEE region code (SPEC S4.3)
FRANCE_REGION_TO_INSEE = {
    "Île-de-France": "11",
    "Centre-Val de Loire": "24",
    "Bourgogne-Franche-Comté": "27",
    "Normandie": "28",
    "Hauts-de-France": "32",
    "Grand Est": "44",
    "Pays de la Loire": "52",
    "Bretagne": "53",
    "Nouvelle-Aquitaine": "75",
    "Occitanie": "76",
    "Auvergne-Rhône-Alpes": "84",
    "Provence-Alpes-Côte-d'Azur": "93",
    "Corse": "94",
    "Guadeloupe": "01",
    "Martinique": "02",
    "Guyane française": "03",
    "Réunion": "04",
    "Mayotte": "06",
}

# France: overseas department iso_3166_2 suffix (after stripping "FR-") -> INSEE dept code
# (SPEC S4.3). Metropolitan codes (incl. "2A"/"2B") are used as-is.
FRANCE_OVERSEAS_DEPT = {
    "GP": "971",  # Guadeloupe
    "MQ": "972",  # Martinique
    "GF": "973",  # Guyane française
    "RE": "974",  # Réunion
    "YT": "976",  # Mayotte
}

# Britain: gu_a3 -> English nation name (SPEC S4.4)
GBR_NATION_NAMES = {
    "ENG": "England",
    "SCT": "Scotland",
    "WLS": "Wales",
    "NIR": "Northern Ireland",
}

# Census STATEFP codes for territories, excluded everywhere (SPEC S4.5)
USA_TERRITORY_STATEFP = {"60", "66", "69", "72", "78"}

# national_conformed neighbour lists (SPEC S2 p.8, S4.5) -- explicit, not bbox-derived.
# (A bbox-envelope restriction of "other countries" is unsafe here: Alaska alone would
# blow the USA bbox out to nearly global extent. Using the named neighbours directly is
# both exact and cheap -- see PREFLIGHT_BND_v0_1.md S7.5/S7.13 for the discarded approach.)
USA_NEIGHBOUR_ISO3 = ["CAN", "MEX"]
NOR_NEIGHBOUR_ISO3 = ["SWE", "FIN", "RUS"]

# ADM0 unit_id overrides fallback columns expected in boundaries/adm0_overrides.csv
ADM0_OVERRIDES_COLUMNS = ["ADM0_A3", "NAME_NE", "iso3", "adm0_status", "reason"]


# --------------------------------------------------------------------------
# Small utilities
# --------------------------------------------------------------------------

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def today_str() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg: str, t0: Optional[float] = None) -> None:
    if t0 is None:
        print(msg, flush=True)
    else:
        print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


class BuildLogger:
    """Collects build_log.json entries -- internal kitchen, never published on the
    site (ADR v6 S6.1). Separate from meta.json."""

    def __init__(self):
        self.entries: list[dict] = []

    def add(self, **kwargs) -> None:
        entry = {"at": now_iso(), **kwargs}
        self.entries.append(entry)

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Geometry primitives -- precision grid + make_valid around every boolean op
# --------------------------------------------------------------------------

def clean(geom: BaseGeometry) -> BaseGeometry:
    """Snap to the fixed precision grid, then make_valid. Apply to inputs before,
    and to results after, every boolean geometry operation (SPEC S4)."""
    if geom is None or geom.is_empty:
        return geom
    g = shapely.make_valid(shapely.set_precision(geom, grid_size=PRECISION_GRID))
    return _to_polygonal(g)


def _to_polygonal(geom: BaseGeometry) -> BaseGeometry:
    """Administrative-area geometry must stay polygonal. Precision-snapping and
    make_valid can leave a degenerate, zero-area LineString/Point sliver sitting
    alongside the real polygon(s) inside a GeometryCollection (seen in practice on
    Akershus, NOR-1-32, after conforming) -- drop those, keep only the
    Polygon/MultiPolygon parts. A GeoJSON writer cannot serialise a
    GeometryCollection the same way as a Polygon, so leaving this in would also
    break output, not just look untidy."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
        if not polys:
            return geom  # nothing polygonal at all -- surface it downstream rather than hide it
        merged = polys[0] if len(polys) == 1 else unary_union(polys)
        return shapely.make_valid(merged)
    return geom  # bare LineString/Point -- should not happen for area data; left as-is to surface loudly


def clean_series(geoms: gpd.GeoSeries) -> gpd.GeoSeries:
    return geoms.apply(clean)


def ensure_crs(gdf: gpd.GeoDataFrame, expected: Optional[str] = None) -> gpd.GeoDataFrame:
    """Require an explicit CRS -- never assume one. If `expected` is given and differs
    from what the file declares, this is not an error (sources legitimately differ --
    e.g. Kartverket fylke is EPSG:3135, kommuner is EPSG:25833) but it must be reprojected
    explicitly by the caller, never silently relabelled."""
    if gdf.crs is None:
        raise ValueError("Input file has no CRS -- refusing to guess one (ADR v6 S10 lesson).")
    return gdf


def to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = ensure_crs(gdf)
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(CRS_WGS84)
    return gdf


def to_equal_area(geoms) -> gpd.GeoSeries:
    """Reproject a GeoSeries (assumed EPSG:4326) to the equal-area CRS for area math."""
    if not isinstance(geoms, gpd.GeoSeries):
        geoms = gpd.GeoSeries(geoms, crs=CRS_WGS84)
    elif geoms.crs is None:
        geoms = geoms.set_crs(CRS_WGS84)
    return geoms.to_crs(CRS_EQUAL_AREA)


def area_km2(geom: BaseGeometry) -> float:
    """Area of a single EPSG:4326 geometry, in km^2, via EPSG:6933."""
    if geom is None or geom.is_empty:
        return 0.0
    return float(to_equal_area(gpd.GeoSeries([geom])).iloc[0].area) / 1e6


def explode_parts(geom: BaseGeometry) -> list[BaseGeometry]:
    """Split a (Multi)Polygon into a flat list of Polygon parts, dropping empties."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "MultiPolygon":
        return [g for g in geom.geoms if not g.is_empty]
    if geom.geom_type == "GeometryCollection":
        out = []
        for g in geom.geoms:
            out.extend(explode_parts(g))
        return out
    return [geom]


def clean_geodataframe(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["geometry"] = clean_series(gdf.geometry)
    return gdf


def union_clean(geoms: Iterable[BaseGeometry]) -> BaseGeometry:
    """unary_union, then clean() the result. The one place callers should reach for
    instead of importing shapely.ops.unary_union directly, so every union in the
    pipeline gets the same precision-grid + make_valid treatment."""
    return clean(unary_union(list(geoms)))


# --------------------------------------------------------------------------
# ADM0 unit_id rule (SPEC S4.1)
# --------------------------------------------------------------------------

def load_adm0_overrides(path: Path) -> dict[str, tuple[str, str]]:
    """boundaries/adm0_overrides.csv -> {ADM0_A3: (iso3, adm0_status)}."""
    df = pd.read_csv(path, dtype=str)
    out = {}
    for _, row in df.iterrows():
        out[row["ADM0_A3"]] = (row["iso3"], row["adm0_status"])
    return out


def compute_iso3(iso_a3_eh: str, adm0_a3: str, overrides: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """SPEC S4.1 steps 1-2: iso3 = ISO_A3_EH, unless it is "-99", in which case the
    ADM0_A3 code is looked up in boundaries/adm0_overrides.csv. Returns (iso3, adm0_status).
    Raises if a "-99" object is not covered by the overrides table -- that is a build
    error per SPEC (an ADM0 object must never be silently dropped or silently kept as
    "-99")."""
    if iso_a3_eh and iso_a3_eh != "-99":
        return iso_a3_eh, "normal"
    if adm0_a3 in overrides:
        return overrides[adm0_a3]
    raise BuildError(
        f"ADM0 object ADM0_A3={adm0_a3!r} has ISO_A3_EH=-99 and is not covered by "
        f"boundaries/adm0_overrides.csv. SPEC S9: stop and ask."
    )


class BuildError(RuntimeError):
    """Raised for any condition SPEC S9 says should stop the build and ask, rather
    than guess: unit-count mismatch, an unresolved -99, an unmapped France region,
    a parent that does not match the country being processed, etc."""


# --------------------------------------------------------------------------
# Neighbour removal (SPEC S4.5 step 1) and country clip (step 1a)
# --------------------------------------------------------------------------

def remove_encroachment(
    units: gpd.GeoDataFrame,
    neighbours_union: BaseGeometry,
    logger: Optional[BuildLogger] = None,
    unit_id_col: str = "unit_id",
) -> gpd.GeoDataFrame:
    """SPEC S4.5 step 1: U := U - N, applied per-unit. Only units whose geometry
    actually intersects the (prepared) neighbour union are touched -- interior units
    are left untouched, which is both correct and the only way this is fast enough
    on 3144 counties / 357 kommuner (see PREFLIGHT_BND_v0_1.md S7.13)."""
    units = units.copy()
    shapely.prepare(neighbours_union)  # mutates in place; speeds up repeated predicates below
    touch_mask = units.geometry.apply(lambda g: shapely.intersects(g, neighbours_union))
    n_touched = int(touch_mask.sum())
    log(f"    encroachment check: {n_touched}/{len(units)} units touch the neighbour union")
    for idx in units.index[touch_mask]:
        before = units.at[idx, "geometry"]
        before_km2 = area_km2(before)
        after = clean(shapely.difference(before, neighbours_union))
        after_km2 = area_km2(after)
        removed = before_km2 - after_km2
        units.at[idx, "geometry"] = after
        if removed > 1e-6 and logger is not None:
            logger.add(
                step="remove_encroachment",
                unit_id=units.at[idx, unit_id_col],
                removed_km2=round(removed, 4),
            )
    return units


def clip_to_country(
    units: gpd.GeoDataFrame, country_poly: BaseGeometry, logger: Optional[BuildLogger] = None,
    unit_id_col: str = "unit_id",
) -> gpd.GeoDataFrame:
    """SPEC S4.5 step 1a (amendment 1, ARCH_to_CODE_BND_go_v0_1.md): for a national
    source whose polygons include open water (Norway/Inndelingsbase has no coastline
    of its own), the DISPLAY geometry is clipped to the country polygon from the
    framework: U := U n P. Not applied to the USA (Census cb is already coast-clipped)."""
    units = units.copy()
    total_sea_removed = 0.0
    for idx in units.index:
        before = units.at[idx, "geometry"]
        before_km2 = area_km2(before)
        after = clean(shapely.intersection(before, country_poly))
        after_km2 = area_km2(after)
        total_sea_removed += before_km2 - after_km2
        units.at[idx, "geometry"] = after
    if logger is not None:
        logger.add(step="clip_to_country_1a", sea_removed_km2=round(total_sea_removed, 2))
    log(f"    clip-to-country (1a): removed {total_sea_removed:.2f} km^2 of open water for display")
    return units


# --------------------------------------------------------------------------
# Gap finding + classification + distribution (SPEC S4.5 steps 2-5)
# --------------------------------------------------------------------------

@dataclass
class GapReport:
    water_km2: float = 0.0
    water_n: int = 0
    coast_km2: float = 0.0
    coast_n: int = 0
    land_km2_initial: float = 0.0
    land_n_initial: int = 0
    land_km2_residual: float = 0.0
    land_n_residual: int = 0
    iterations: int = 0


def find_gap_parts(
    country_poly: BaseGeometry,
    units_union: BaseGeometry,
    exclude: Optional[BaseGeometry] = None,
) -> list[BaseGeometry]:
    """SPEC S4.5 step 2: G := P - union(U), split into parts. `exclude` removes parts
    already covered by ADM1 units taken as-is from NE (Svalbard, for Norway)."""
    gap = clean(shapely.difference(country_poly, units_union))
    if exclude is not None and not gap.is_empty:
        gap = clean(shapely.difference(gap, exclude))
    return [p for p in explode_parts(gap) if area_km2(p) > 1e-6]


def classify_gap_parts(
    parts: list[BaseGeometry], neighbours_union: BaseGeometry, lakes_union: BaseGeometry
) -> tuple[list[BaseGeometry], list[BaseGeometry], list[BaseGeometry]]:
    """SPEC S4.5 step 3 + amendment 2: classify each gap part as water / land / coast.
    `lakes_union` must be the union of the WHOLE ne_10m_lakes layer, not just the
    Great Lakes -- amendment 2 explicitly widens this (Lake St Clair etc. fall in
    on their own)."""
    shapely.prepare(neighbours_union)
    shapely.prepare(lakes_union)
    water, land, coast = [], [], []
    for part in parts:
        part_area = part.area
        if part_area <= 0:
            continue
        lake_overlap = shapely.intersection(part, lakes_union).area
        if lake_overlap / part_area >= WATER_GAP_FRACTION:
            water.append(part)
            continue
        touches = shapely.dwithin(part, neighbours_union, BOUNDARY_TOUCH_TOL_DEG)
        if touches:
            land.append(part)
        else:
            coast.append(part)
    return water, land, coast


def assign_land_gaps(
    units: gpd.GeoDataFrame,
    land_parts: list[BaseGeometry],
    logger: Optional[BuildLogger] = None,
    unit_id_col: str = "unit_id",
) -> gpd.GeoDataFrame:
    """SPEC S4.5 step 4: each land-type gap part is merged into the unit with the
    LONGEST shared boundary with that part (not simply the nearest). Falls back to
    the geometrically nearest unit if a part does not touch any unit at all (should
    not normally happen)."""
    if not land_parts:
        return units
    units = units.copy()
    boundaries = units.geometry.boundary.values
    tree = shapely.STRtree(boundaries)
    assignments: dict[int, list[BaseGeometry]] = {}
    for part in land_parts:
        part_b = part.boundary
        cand_idx = tree.query(part_b, predicate="intersects")
        if len(cand_idx) == 0:
            # Fallback: geometrically nearest unit boundary.
            nearest_idx = tree.nearest(part_b)
            best_idx = int(nearest_idx)
        else:
            best_idx = int(max(cand_idx, key=lambda i: part_b.intersection(boundaries[i]).length))
        assignments.setdefault(best_idx, []).append(part)
    for pos, parts in assignments.items():
        idx = units.index[pos]
        before = units.at[idx, "geometry"]
        merged = clean(unary_union([before, *parts]))
        added_km2 = sum(area_km2(p) for p in parts)
        units.at[idx, "geometry"] = merged
        if logger is not None:
            logger.add(
                step="assign_land_gap",
                unit_id=units.at[idx, unit_id_col],
                added_km2=round(added_km2, 4),
                n_parts=len(parts),
            )
    return units


def conform_national(
    units: gpd.GeoDataFrame,
    country_poly: BaseGeometry,
    neighbours_union: BaseGeometry,
    lakes_union: BaseGeometry,
    *,
    clip_water: bool,
    exclude_from_gaps: Optional[BaseGeometry] = None,
    logger: Optional[BuildLogger] = None,
    unit_id_col: str = "unit_id",
    max_iterations: int = 5,
) -> tuple[gpd.GeoDataFrame, GapReport]:
    """Full SPEC S4.5 national_conformed pipeline (steps 1, 1a, 2-5) for one country's
    ADM2 (or single-level) units. Returns the conformed units and a GapReport with the
    final water/land/coast breakdown, for the handoff report and for validation check 3."""
    report = GapReport()

    units = remove_encroachment(units, neighbours_union, logger, unit_id_col)
    if clip_water:
        units = clip_to_country(units, country_poly, logger, unit_id_col)

    for iteration in range(1, max_iterations + 1):
        units_union = clean(unary_union(units.geometry.values))
        parts = find_gap_parts(country_poly, units_union, exclude=exclude_from_gaps)
        water, land, coast = classify_gap_parts(parts, neighbours_union, lakes_union)

        water_km2 = sum(area_km2(p) for p in water)
        coast_km2 = sum(area_km2(p) for p in coast)
        land_km2 = sum(area_km2(p) for p in land)

        if iteration == 1:
            report.water_km2, report.water_n = water_km2, len(water)
            report.coast_km2, report.coast_n = coast_km2, len(coast)
            report.land_km2_initial, report.land_n_initial = land_km2, len(land)

        report.iterations = iteration
        log(f"    conform iteration {iteration}: water={water_km2:.2f}km2({len(water)}) "
            f"land={land_km2:.2f}km2({len(land)}) coast={coast_km2:.2f}km2({len(coast)})")

        if land_km2 <= CONFORM_RESIDUAL_TOL_KM2 or not land:
            report.land_km2_residual, report.land_n_residual = land_km2, len(land)
            break

        units = assign_land_gaps(units, land, logger, unit_id_col)
        report.land_km2_residual, report.land_n_residual = land_km2, len(land)

    return units, report


# --------------------------------------------------------------------------
# Dissolve / nesting helpers
# --------------------------------------------------------------------------

def dissolve_clean(gdf: gpd.GeoDataFrame, by: str, agg: Optional[dict] = None) -> gpd.GeoDataFrame:
    """gpd.dissolve, then re-clean the merged geometries (a dissolve is a union under
    the hood and can need the same set_precision/make_valid treatment as any other
    boolean op)."""
    out = gdf.dissolve(by=by, aggfunc=agg or "first", as_index=False)
    out["geometry"] = clean_series(out.geometry)
    return out


def nesting_fraction(child: BaseGeometry, parent: BaseGeometry) -> float:
    """Fraction of `child`'s area covered by `parent` (SPEC S4.2 / S5.10 p.4)."""
    child_area = area_km2(child)
    if child_area <= 0:
        return 1.0
    inter_area = area_km2(shapely.intersection(child, parent))
    return inter_area / child_area


# --------------------------------------------------------------------------
# Overlap check (validation check 1, also useful as a build-time sanity check)
# --------------------------------------------------------------------------

def pairwise_overlaps(gdf: gpd.GeoDataFrame, tol_km2: float = OVERLAP_TOL_KM2) -> list[dict]:
    """All pairs of units in `gdf` (assumed same level) whose intersection area
    exceeds `tol_km2`. O(n log n) via spatial index, not O(n^2)."""
    geoms = gdf.geometry.values
    ids = gdf["unit_id"].values
    tree = shapely.STRtree(geoms)
    out = []
    seen = set()
    for i, g in enumerate(geoms):
        cand = tree.query(g, predicate="intersects")
        for j in cand:
            j = int(j)
            if j <= i:
                continue
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)
            inter = shapely.intersection(g, geoms[j])
            if inter.is_empty:
                continue
            a = area_km2(inter)
            if a > tol_km2:
                out.append({"unit_a": ids[i], "unit_b": ids[j], "overlap_km2": round(a, 4)})
    return out


# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------

def write_parquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gdf.sort_values("unit_id").reset_index(drop=True)
    gdf.to_parquet(path)


def write_geojson_gz(gdf: gpd.GeoDataFrame, path: Path, precision: int = 6) -> None:
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gdf.sort_values("unit_id").reset_index(drop=True)
    raw = gdf.to_json(na="null", drop_id=True)
    # Round coordinate precision post-hoc via GDAL's COORDINATE_PRECISION would need
    # a temp file; simplest robust route is geopandas' own to_json + re-dump through
    # the shapely mapping with rounded coords.
    obj = json.loads(raw)
    for feat in obj.get("features", []):
        feat["geometry"] = _round_geojson_geom(feat["geometry"], precision)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _round_geojson_geom(geom: dict, precision: int) -> dict:
    def rnd(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, precision) for c in coords]
        return [rnd(c) for c in coords]

    if geom is None:
        return geom
    geom = dict(geom)
    if "coordinates" in geom:
        geom["coordinates"] = rnd(geom["coordinates"])
    elif "geometries" in geom:  # GeometryCollection -- defense in depth; clean() should
        # already have stripped these down to a plain Polygon/MultiPolygon before this
        # point, but round any that slip through rather than crash on them.
        geom["geometries"] = [_round_geojson_geom(g, precision) for g in geom["geometries"]]
    return geom


def read_registry(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)
