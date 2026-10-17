#!/usr/bin/env python3
"""
validate_boundaries.py -- SPEC_BND_boundaries_v0_1.md S5 checks plus the v0.2.0 checks 7-10
(SPEC_BND_boundaries_v0_2_0.md S2.1 p.6, S2.3, S2.5, S2.6), run against the *output* files only
(not against build_boundaries.py's in-memory state).

v0.2.0 additions:
  check 7  land coverage: NE admin-1 land not covered by ADM0 (stop >= 100 km2, report >= 1 km2)
  check 8  P8 nested units (stop at >= 5 in a country; table in the report)
  check 9  reconciliation with v0.1.0 unit_hashes.csv (--prev-hashes; skipped with a note if not given)
  check 10 contested_areas layer
  check 11 codes and names against Unicode CLDR release-48-2 (S2.4a)
  report   per-unit clipping losses of the plan ADM1 (read from build_log.json)

Run (from repo root, after build_boundaries.py):
    # first run -- also generates the ADM0 hole whitelist proposal for V to review in QGIS:
    python scripts\\boundaries\\validate_boundaries.py --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.2.0" --sources-dir "D:\\GISData\\Boundaries\\sources" --init-whitelist
    # after V has reviewed boundaries/holes_whitelist.geojson and it is committed:
    python scripts\\boundaries\\validate_boundaries.py --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.2.0" --sources-dir "D:\\GISData\\Boundaries\\sources" --prev-hashes "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.1.0\\unit_hashes.csv"

Writes validation_report.json and validation_report.md into --out-dir.
Exit code 1 if any of checks 1-5 or 7-11 fails; check 6 is report-only and never fails the run.

--init-whitelist additionally writes boundaries/holes_whitelist.geojson (repo, not
committed by this script -- SPEC S5: "в git -- только после ответа V") and
display/adm0_disputed_unassigned.parquet + .geojson.gz (kind == disputed_unassigned
holes only, with a `pov` column) into --out-dir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnd_common as c  # noqa: E402
import bnd_plan as bp  # noqa: E402


def log(msg: str) -> None:
    print(f"[validate] {msg}", flush=True)


# --------------------------------------------------------------------------
# Reference table for the ADM0 hole whitelist (SPEC S5), used to label holes
# found by --init-whitelist. Matched by centroid proximity / bounding range --
# the actual geometry always comes from this run's own ADM0 union, never from
# this table; the table only supplies label/kind for V's QGIS review.
# --------------------------------------------------------------------------

_SINGLETON_HOLES = [
    # (expected_area_km2, lon, lat, label, kind)
    (397056, 50.8, 41.6, "Caspian Sea", "sea"),
    (10876, 28.4, 9.7, "Abyei", "disputed_unassigned"),
    (2088, 77.3, 35.4, "Siachen Glacier", "disputed_unassigned"),
    (1409, -73.3, -49.5, "Southern Patagonian Ice Field", "disputed_unassigned"),
    (268, -56.0, -31.0, "Rincón de Artigas", "disputed_unassigned"),
]
# Group references: a bounding box + a descending-area-ordered label list. Any hole
# whose centroid falls in the box is assigned to this group; within a group, holes
# are matched to labels by descending area, matching the reference table's own order.
_GROUP_HOLES = [
    dict(lon=(35.1, 35.8), lat=(4.5, 4.9), kind="disputed_unassigned",
         label="Ilemi Triangle", ref_areas=[3352, 49, 17]),
    dict(lon=(33.5, 35.5), lat=(21.6, 23.0), kind="sliver",
         label="Bir Tawil / Halaib slivers", ref_areas=[10.8, 8.4, 3.8, 0.6]),
]


def classify_holes(holes: list) -> list[dict]:
    """holes: list of (geometry, area_km2, lon, lat). Returns a row per hole with
    label/kind, either matched against the SPEC S5 reference table or flagged
    UNKNOWN for V to classify by hand in QGIS."""
    remaining = list(holes)
    rows = []

    # 1) singletons -- nearest centroid within a generous 3-degree tolerance
    for exp_area, exp_lon, exp_lat, label, kind in _SINGLETON_HOLES:
        best = None
        best_d = None
        for h in remaining:
            geom, area_km2, lon, lat = h
            d = ((lon - exp_lon) ** 2 + (lat - exp_lat) ** 2) ** 0.5
            if d < 3.0 and (best_d is None or d < best_d):
                best, best_d = h, d
        if best is not None:
            geom, area_km2, lon, lat = best
            rows.append(dict(area_km2=round(area_km2, 2), lon=round(lon, 2), lat=round(lat, 2),
                              label=label, kind=kind, geometry=geom))
            remaining.remove(best)

    # 2) groups -- match by bounding box, then pair by descending area
    for grp in _GROUP_HOLES:
        # h = (geom, area_km2, lon, lat) -> lon is h[2], lat is h[3]
        in_box = [h for h in remaining if grp["lon"][0] <= h[2] <= grp["lon"][1] and grp["lat"][0] <= h[3] <= grp["lat"][1]]
        in_box.sort(key=lambda h: -h[1])
        for h, ref_area in zip(in_box, grp["ref_areas"]):
            geom, area_km2, lon, lat = h
            rows.append(dict(area_km2=round(area_km2, 2), lon=round(lon, 2), lat=round(lat, 2),
                              label=grp["label"], kind=grp["kind"], geometry=geom))
            remaining.remove(h)

    # 3) anything left is unmatched -- surface it, do not guess
    for geom, area_km2, lon, lat in remaining:
        rows.append(dict(area_km2=round(area_km2, 2), lon=round(lon, 2), lat=round(lat, 2),
                          label="UNKNOWN -- review in QGIS", kind="sliver", geometry=geom))
    return rows


def find_adm0_holes(adm0: gpd.GeoDataFrame) -> list[dict]:
    union = c.union_clean(adm0.geometry.values)
    parts = c.explode_parts(union)
    holes_geoms = []
    for part in parts:
        for ring in part.interiors:
            holes_geoms.append(shapely.Polygon(ring))
    holes = []
    for g in holes_geoms:
        area = c.area_km2(g)
        if area < 1e-4:
            continue
        centroid = g.centroid
        holes.append((g, area, centroid.x, centroid.y))
    return classify_holes(holes)


# --------------------------------------------------------------------------
# Check 1 -- overlaps
# --------------------------------------------------------------------------

def check_overlaps(adm0, adm1, adm2, registry=None) -> dict:
    """Check 1. All pairs > OVERLAP_TOL_KM2 (0.01) are listed in the report. A pair fails the check unless it is a
    pair of units from DIFFERENT countries where at least one country is national_conformed (USA, NOR): for those
    the tolerance is CONFORM_RESIDUAL_TOL_KM2 (0.05) -- ARCH6 decision 17.10.2026 (SPEC v0.2.0 r3). Inside a
    country and between NE-based countries the tolerance stays 0.01."""
    nc = set()
    if registry is not None:
        nc = set(registry.loc[registry["method"] == "national_conformed", "iso3"])
    result = {}
    for name, gdf in [("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)]:
        iso = dict(zip(gdf["unit_id"], gdf["iso3"]))
        overlaps = c.pairwise_overlaps(gdf, tol_km2=c.OVERLAP_TOL_KM2)
        failing, relaxed = [], []
        for o in overlaps:
            ia, ib = iso[o["unit_a"]], iso[o["unit_b"]]
            ok = (ia != ib) and (ia in nc or ib in nc) and o["overlap_km2"] <= c.CONFORM_RESIDUAL_TOL_KM2
            (relaxed if ok else failing).append(o)
        result[name] = {"n_pairs_above_0_01": len(overlaps), "n_failing": len(failing),
                        "n_accepted_relaxed_tol_0_05": len(relaxed),
                        "failing": failing[:50], "accepted_relaxed": relaxed[:50]}
    passed = all(v["n_failing"] == 0 for v in result.values())
    return {"passed": passed, "tolerances_km2": {"default": c.OVERLAP_TOL_KM2,
            "different_countries_one_national_conformed": c.CONFORM_RESIDUAL_TOL_KM2}, "detail": result}


# --------------------------------------------------------------------------
# Check 2 -- ADM0 holes vs whitelist
# --------------------------------------------------------------------------

def check_holes(adm0: gpd.GeoDataFrame, whitelist_path: Path) -> dict:
    current = find_adm0_holes(adm0)
    if not whitelist_path.exists():
        return {"passed": False, "reason": f"{whitelist_path} does not exist -- run with --init-whitelist first, "
                                            "have V review it in QGIS, and commit it.",
                "current_holes": [{k: v for k, v in h.items() if k != "geometry"} for h in current]}
    wl = gpd.read_file(whitelist_path)
    unmatched_current = []
    for h in current:
        g = h["geometry"]
        best = None
        for _, wrow in wl.iterrows():
            inter = shapely.intersection(g, wrow.geometry)
            sd_area = c.area_km2(shapely.symmetric_difference(g, wrow.geometry))
            if sd_area <= c.HOLE_WHITELIST_TOL_KM2:
                best = wrow
                break
        if best is None:
            unmatched_current.append({k: v for k, v in h.items() if k != "geometry"})
    passed = len(unmatched_current) == 0
    return {"passed": passed, "n_current_holes": len(current), "n_whitelisted": len(wl),
            "unmatched_current_holes": unmatched_current}


# --------------------------------------------------------------------------
# Check 3 -- USA/Norway conforming residuals, re-measured independently from output
# --------------------------------------------------------------------------

def check_conform_residual(adm0: gpd.GeoDataFrame, adm2: gpd.GeoDataFrame, lakes_union, iso3: str, neighbour_iso3: list[str]) -> dict:
    units = adm2[adm2["iso3"] == iso3]
    country_poly = adm0.loc[adm0["unit_id"] == iso3, "geometry"].iloc[0]
    neighbours = c.union_clean(adm0.loc[adm0["unit_id"].isin(neighbour_iso3), "geometry"])

    units_union = c.union_clean(units.geometry.values)
    encroach = c.area_km2(shapely.intersection(units_union, neighbours))

    parts = c.find_gap_parts(country_poly, units_union)
    _water, land, _coast = c.classify_gap_parts(parts, neighbours, lakes_union)
    land_km2 = sum(c.area_km2(p) for p in land)

    passed = encroach <= c.CONFORM_RESIDUAL_TOL_KM2 and land_km2 <= c.CONFORM_RESIDUAL_TOL_KM2
    return {"passed": passed, "encroachment_km2": round(encroach, 4), "land_gap_km2": round(land_km2, 4),
            "tolerance_km2": c.CONFORM_RESIDUAL_TOL_KM2, "n_land_fragments": len(land)}


# --------------------------------------------------------------------------
# Check 4 -- nesting
# --------------------------------------------------------------------------

def check_nesting(adm0, adm1, adm2, registry: pd.DataFrame) -> dict:
    result = {}

    # ADM2 in its own ADM1 -- always, for every country that has ADM2
    for iso3 in adm2["iso3"].unique():
        children = adm2[adm2["iso3"] == iso3]
        parents = adm1[adm1["iso3"] == iso3].set_index("unit_id")["geometry"]
        bad = []
        for row in children.itertuples():
            parent_geom = parents.get(row.parent_id)
            if parent_geom is None:
                bad.append((row.unit_id, "parent_id not found in ADM1"))
                continue
            frac = c.nesting_fraction(row.geometry, parent_geom)
            if frac < c.NESTING_MIN_FRACTION:
                bad.append((row.unit_id, round(frac, 5)))
        result[f"{iso3}_ADM2_in_ADM1"] = {"passed": len(bad) == 0, "n_checked": len(children), "bad": bad[:50]}

    # ADM1 in ADM0 -- only for ne_dissolve/ne_as_is countries (France, Britain).
    # national_conformed countries (USA, Norway) are exempt per ADR v6 S5.10 p.4 --
    # their own coastline can legitimately extend beyond the NE ADM0 contour into the
    # sea; they are checked instead via check 3 (conform residual).
    exempt = set()
    if registry is not None:
        exempt = set(registry.loc[registry["method"] == "national_conformed", "iso3"])
    for iso3 in adm1["iso3"].unique():
        if iso3 in exempt:
            continue
        children = adm1[adm1["iso3"] == iso3]
        parent_geom = adm0.loc[adm0["unit_id"] == iso3, "geometry"]
        if len(parent_geom) == 0:
            continue
        parent_geom = parent_geom.iloc[0]
        bad = []
        for row in children.itertuples():
            frac = c.nesting_fraction(row.geometry, parent_geom)
            if frac < c.NESTING_MIN_FRACTION:
                bad.append((row.unit_id, round(frac, 5)))
        result[f"{iso3}_ADM1_in_ADM0"] = {"passed": len(bad) == 0, "n_checked": len(children), "bad": bad}

    passed = all(v["passed"] for v in result.values())
    return {"passed": passed, "detail": result}


# --------------------------------------------------------------------------
# Check 5 -- unit counts, unit_id uniqueness, parent_id present
# --------------------------------------------------------------------------

def check_counts(adm0, adm1, adm2, registry: pd.DataFrame) -> dict:
    problems = []

    for name, gdf in [("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)]:
        dupes = gdf["unit_id"][gdf["unit_id"].duplicated()].tolist()
        if dupes:
            problems.append(f"{name}: duplicate unit_id: {dupes}")
        if name != "ADM0":
            missing_parent = gdf[gdf["parent_id"].isna() | (gdf["parent_id"] == "")]
            if len(missing_parent):
                problems.append(f"{name}: {len(missing_parent)} row(s) missing parent_id: "
                                 f"{missing_parent['unit_id'].tolist()[:20]}")

    if len(adm0) != c.ADM0_EXPECTED_UNITS:
        problems.append(f"ADM0 count = {len(adm0)}, expected {c.ADM0_EXPECTED_UNITS}")

    if registry is not None:
        for _, row in registry.iterrows():
            gdf = adm1 if row["level"] == "ADM1" else adm2
            n = int((gdf["iso3"] == row["iso3"]).sum())
            expected = int(row["expected_units"])
            if n != expected:
                problems.append(f"{row['iso3']} {row['level']}: {n} units, expected {expected} (boundary_registry.csv)")

    return {"passed": len(problems) == 0, "problems": problems}


# --------------------------------------------------------------------------
# Check 6 -- report only: US county centroid in same-code NE county (except CT)
# --------------------------------------------------------------------------

def check_county_centroids(usa_analysis_adm2: gpd.GeoDataFrame, ne_adm2_counties: gpd.GeoDataFrame) -> dict:
    ne = c.to_wgs84(ne_adm2_counties)
    # Natural Earth's US county layer keys on FIPS, prefixed "US" + 5-digit code
    # (e.g. "US53073"), not the bare GEOID -- confirmed empirically on the actual file.
    if "FIPS" not in ne.columns:
        return {"note": "ne_10m_admin_2_counties has no FIPS column -- skipped.", "mismatches": []}
    ne_us = ne[ne["FIPS"].astype(str).str.match(r"^US\d{5}$")].reset_index(drop=True)
    tree = shapely.STRtree(ne_us.geometry.values)
    fips_values = ne_us["FIPS"].astype(str).values

    mismatches = []
    checked = 0
    for row in usa_analysis_adm2.itertuples():
        geoid = row.unit_id.replace("USA-2-", "")
        if geoid[:2] == "09":  # Connecticut -- known exception (SPEC S5 check 6)
            continue
        checked += 1
        centroid = row.geometry.centroid
        cand = tree.query(centroid, predicate="intersects")
        matched = any(fips_values[i] == "US" + geoid for i in cand)
        if not matched:
            mismatches.append(row.unit_id)
    return {"n_checked": checked, "n_mismatches": len(mismatches), "mismatches": mismatches[:100]}


# --------------------------------------------------------------------------
# v0.2.0 checks 7-10
# --------------------------------------------------------------------------

def check_land_coverage(ne_adm1_path: Path, adm0, whitelist_path: Path) -> dict:
    return bp.land_coverage(gpd.read_file(ne_adm1_path), adm0, whitelist_path)


def check_nested_units(adm1) -> dict:
    return bp.check_nested(bp.find_nested_units(adm1))


def check_reconciliation(prev_hashes: Path | None, out_dir: Path, boundaries_dir: Path) -> dict:
    if prev_hashes is None or not Path(prev_hashes).exists():
        return {"passed": True, "skipped": True, "note": "no --prev-hashes given: reconciliation with the previous release not run"}
    plan = bp.load_plan(boundaries_dir / "adm1_plan.csv")
    ov_path = boundaries_dir / "name_overrides.csv"
    ov_ids = set(pd.read_csv(ov_path, dtype=str)["unit_id"]) if ov_path.exists() else set()
    patches = pd.read_csv(boundaries_dir / "adm0_patches.csv", dtype=str)
    res = bp.reconcile_with_previous(Path(prev_hashes), out_dir / "unit_hashes.csv",
                                     expected_geom_changed=set(patches["iso3"]), name_override_ids=ov_ids,
                                     plan_iso3=set(plan["iso3"]))
    # new rows: exactly the planned ADM1 units, all with parent_id in the plan countries
    new = pd.read_csv(out_dir / "unit_hashes.csv", dtype=str)
    prev = pd.read_csv(prev_hashes, dtype=str)
    added = set(new["unit_id"]) - set(prev["unit_id"])
    if added != set(plan["unit_id"]):
        res["problems"].append(f"added unit_id differ from the plan: {len(added ^ set(plan['unit_id']))} differences")
        res["passed"] = False
    res["n_added_expected_plan"] = len(plan)
    res["n_plan_countries"] = int(plan["iso3"].nunique())
    res["passed"] = res["passed"] and not res["problems"]
    return res


def check_contested(out_dir: Path, boundaries_dir: Path, adm0, adm1) -> dict:
    layer = gpd.read_parquet(out_dir / "display" / "contested_areas.parquet")
    csv_path = boundaries_dir / "contested_areas.csv"
    problems = []
    n_csv = 0
    if csv_path.exists():
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        n_csv = len(df)
        frame = dict(zip(adm0["unit_id"], adm0.geometry))
        frame.update(dict(zip(adm1["unit_id"], adm1.geometry)))
        adm0_ids = set(adm0["unit_id"])
        if len(layer) != n_csv:
            problems.append(f"layer has {len(layer)} zones, CSV has {n_csv} rows")
        for r in df.itertuples():
            ids = [x.strip() for x in r.frame_unit_ids.split(";") if x.strip()]
            absent = [x for x in ids if x not in frame]
            if absent or not ids:
                problems.append(f"{r.area_id}: frame_unit_ids not found: {absent}")
                continue
            expect = c.union_clean([frame[x] for x in ids])
            got = layer.loc[layer["area_id"] == r.area_id, "geometry"]
            if len(got) != 1:
                problems.append(f"{r.area_id}: not in the layer")
                continue
            sd = c.area_km2(shapely.symmetric_difference(got.iloc[0], expect))
            if sd > 1e-6:
                problems.append(f"{r.area_id}: geometry differs from the union of frame units by {sd:.6f} km2")
            for fld in ("controlled_by", "claimed_by"):
                bad = [x for x in getattr(r, fld).split(";") if x.strip() not in adm0_ids]
                if bad:
                    problems.append(f"{r.area_id}: {fld} not ADM0 unit(s): {bad}")
            for fld in ("name", "label"):
                if not getattr(r, fld).isascii():
                    problems.append(f"{r.area_id}: {fld} is not English/ASCII (G7)")
    ov = c.pairwise_overlaps(layer.assign(unit_id=layer["area_id"])) if len(layer) > 1 else []
    if ov:
        problems.append(f"zones overlap: {ov}")
    return {"passed": not problems, "problems": problems, "n_zones": len(layer), "n_csv_rows": n_csv,
            "note": "empty layer is allowed (no rows in contested_areas.csv)" if n_csv == 0 else ""}


# --------------------------------------------------------------------------
# --init-whitelist outputs
# --------------------------------------------------------------------------

def write_whitelist_and_disputed_layer(adm0: gpd.GeoDataFrame, out_dir: Path, boundaries_dir: Path, pov: str) -> None:
    holes = find_adm0_holes(adm0)
    wl_rows = [{"area_km2": h["area_km2"], "lon": h["lon"], "lat": h["lat"],
                "label": h["label"], "kind": h["kind"], "geometry": h["geometry"]} for h in holes]
    wl_gdf = gpd.GeoDataFrame(wl_rows, crs=c.CRS_WGS84)
    boundaries_dir.mkdir(parents=True, exist_ok=True)
    wl_path = boundaries_dir / "holes_whitelist.geojson"
    wl_gdf.to_file(wl_path, driver="GeoJSON")
    log(f"wrote {wl_path} ({len(wl_gdf)} holes) -- REVIEW IN QGIS BEFORE COMMITTING (SPEC S5)")
    unknown = [h for h in holes if h["label"].startswith("UNKNOWN")]
    if unknown:
        log(f"  ! {len(unknown)} hole(s) could not be matched to the SPEC S5 reference table -- "
            f"flagged UNKNOWN, needs manual review: "
            f"{[(round(h['area_km2'],1), h['lon'], h['lat']) for h in unknown]}")

    disputed = wl_gdf[wl_gdf["kind"] == "disputed_unassigned"].copy()
    disputed["pov"] = pov
    c.write_parquet(
        gpd.GeoDataFrame({"unit_id": [f"DISPUTED-{i}" for i in range(len(disputed))],
                           "label": disputed["label"].values, "area_km2": disputed["area_km2"].values,
                           "pov": disputed["pov"].values, "geometry": disputed.geometry.values}, crs=c.CRS_WGS84),
        out_dir / "display" / "adm0_disputed_unassigned.parquet",
    )
    c.write_geojson_gz(
        gpd.GeoDataFrame({"unit_id": [f"DISPUTED-{i}" for i in range(len(disputed))],
                           "label": disputed["label"].values, "area_km2": disputed["area_km2"].values,
                           "pov": disputed["pov"].values, "geometry": disputed.geometry.values}, crs=c.CRS_WGS84),
        out_dir / "display" / "adm0_disputed_unassigned.geojson.gz",
    )
    log(f"wrote display/adm0_disputed_unassigned.* ({len(disputed)} zones, pov={pov})")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    ap.add_argument("--sources-dir", required=True, type=Path,
                     help="the same --sources-dir used for build_boundaries.py. Required: check 3 "
                          "(mandatory, affects exit code) reads ne_10m_lakes from here, and check 6 "
                          "(report-only) reads ne_10m_admin_2_counties from here.")
    ap.add_argument("--prev-hashes", type=Path, default=None,
                     help="unit_hashes.csv of the previous release (v0.1.0) for the S2.5 reconciliation (check 9)")
    ap.add_argument("--init-whitelist", action="store_true",
                     help="(re)compute boundaries/holes_whitelist.geojson and display/adm0_disputed_unassigned.* "
                          "from the current ADM0 output, instead of checking against a committed whitelist.")
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    adm0 = gpd.read_parquet(out_dir / "display" / "adm0.parquet")
    adm1 = gpd.read_parquet(out_dir / "display" / "adm1.parquet")
    adm2 = gpd.read_parquet(out_dir / "display" / "adm2.parquet")
    manifest = json.loads((args.sources_dir / "sources_manifest.json").read_text(encoding="utf-8"))
    ne_lakes_path = manifest.get("ne_lakes", {}).get("path")
    if ne_lakes_path is None:
        raise c.BuildError(
            "check 3 needs ne_10m_lakes, but sources_manifest.json in --sources-dir has no "
            "'ne_lakes' entry -- re-run fetch_boundary_sources.py."
        )
    lakes_union = c.union_clean(c.to_wgs84(gpd.read_file(ne_lakes_path)).geometry.values)

    registry_path = args.boundaries_dir / "boundary_registry.csv"
    registry = c.read_registry(registry_path) if registry_path.exists() else None

    meta_path = out_dir / "meta.json"
    pov = json.loads(meta_path.read_text(encoding="utf-8"))["adm0_pov"] if meta_path.exists() else "usa"

    if args.init_whitelist:
        write_whitelist_and_disputed_layer(adm0, out_dir, args.boundaries_dir, pov)

    log("check 1: overlaps...")
    r1 = check_overlaps(adm0, adm1, adm2, registry)
    log(f"  passed={r1['passed']}")

    log("check 2: ADM0 holes vs whitelist...")
    r2 = check_holes(adm0, args.boundaries_dir / "holes_whitelist.geojson")
    log(f"  passed={r2['passed']}")

    log("check 3: USA/Norway conforming residuals (re-measured from output)...")
    r3_usa = check_conform_residual(adm0, adm2, lakes_union, "USA", c.USA_NEIGHBOUR_ISO3)
    r3_nor = check_conform_residual(adm0, adm2, lakes_union, "NOR", c.NOR_NEIGHBOUR_ISO3)
    r3 = {"passed": r3_usa["passed"] and r3_nor["passed"], "USA": r3_usa, "NOR": r3_nor}
    log(f"  passed={r3['passed']} (USA encroach={r3_usa['encroachment_km2']}km2 land={r3_usa['land_gap_km2']}km2; "
        f"NOR encroach={r3_nor['encroachment_km2']}km2 land={r3_nor['land_gap_km2']}km2)")

    log("check 4: nesting...")
    r4 = check_nesting(adm0, adm1, adm2, registry)
    log(f"  passed={r4['passed']}")

    log("check 5: unit counts / unit_id / parent_id...")
    r5 = check_counts(adm0, adm1, adm2, registry)
    log(f"  passed={r5['passed']}" + (f" -- {r5['problems']}" if not r5["passed"] else ""))

    log("check 6 (report only): US county centroids vs NE...")
    ne_counties_path = manifest["ne_adm2_counties"]["path"]
    usa_analysis_adm2 = gpd.read_parquet(out_dir / "analysis" / "USA_adm2_cb2023_500k.parquet")
    r6 = check_county_centroids(usa_analysis_adm2, gpd.read_file(ne_counties_path))
    log(f"  checked={r6.get('n_checked')} mismatches={r6.get('n_mismatches')}")

    ne_adm1_path = Path(manifest["ne_adm1"]["path"])
    log("check 7: land coverage (NE admin-1 vs ADM0)...")
    r7 = check_land_coverage(ne_adm1_path, adm0, args.boundaries_dir / "holes_whitelist.geojson")
    log(f"  passed={r7['passed']} stop={len(r7['stop_ge_100_km2'])} report={len(r7['report_1_to_100_km2'])}")

    log("check 8: P8 nested units...")
    r8 = check_nested_units(adm1)
    log(f"  passed={r8['passed']} max per country={r8['max_per_country']} {r8['per_country']}")

    log("check 9: reconciliation with the previous release...")
    r9 = check_reconciliation(args.prev_hashes, out_dir, args.boundaries_dir)
    log(f"  passed={r9['passed']}" + (f" -- {r9['problems']}" if r9.get("problems") else "")
        + (" (skipped)" if r9.get("skipped") else ""))

    log("check 10: contested_areas...")
    r10 = check_contested(out_dir, args.boundaries_dir, adm0, adm1)
    log(f"  passed={r10['passed']} zones={r10['n_zones']}" + (f" -- {r10['problems']}" if r10["problems"] else ""))

    log("check 11: codes and names vs Unicode CLDR release-48-2...")
    plan_df = bp.load_plan(args.boundaries_dir / "adm1_plan.csv")
    r11 = bp.check_cldr(plan_df, dict(zip(adm1["unit_id"], adm1["name"])), manifest)
    log(f"  passed={r11['passed']} violations={r11['n_violations']} exceptions={[e['unit_id'] for e in r11['exceptions']]}")

    clip_losses = []
    bl_path = out_dir / "build_log.json"
    if bl_path.exists():
        for e in json.loads(bl_path.read_text(encoding="utf-8")):
            if e.get("step") == "plan_clip_losses":
                clip_losses = e.get("losses", [])
    totals = {"ADM0": len(adm0), "ADM1": len(adm1), "ADM2": len(adm2), "countries_with_adm1": int(adm1["iso3"].nunique()),
              "registry_rows": (len(registry) if registry is not None else None)}

    report = {
        "generated_at": c.now_iso(),
        "totals": totals,
        "check_1_overlaps": r1,
        "check_2_adm0_holes": r2,
        "check_3_conform_residual": r3,
        "check_4_nesting": r4,
        "check_5_counts": r5,
        "check_6_county_centroids_report_only": r6,
        "check_7_land_coverage": r7,
        "check_8_nested_units": r8,
        "check_9_reconciliation_with_previous": r9,
        "check_10_contested_areas": r10,
        "check_11_cldr_codes_and_names": r11,
        "plan_adm1_clip_losses": clip_losses,
    }
    overall_passed = all([r1["passed"], r2["passed"], r3["passed"], r4["passed"], r5["passed"],
                           r7["passed"], r8["passed"], r9["passed"], r10["passed"], r11["passed"]])
    report["overall_passed"] = overall_passed

    (out_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    md = ["# validation_report", "", f"generated_at: {report['generated_at']}", "",
          f"**Overall: {'PASSED' if overall_passed else 'FAILED'}**", "",
          "| check | passed |", "|---|---|",
          f"| 1. overlaps | {r1['passed']} |",
          f"| 2. ADM0 holes vs whitelist | {r2['passed']} |",
          f"| 3. USA/NOR conform residual | {r3['passed']} |",
          f"| 4. nesting | {r4['passed']} |",
          f"| 5. counts/unit_id/parent_id | {r5['passed']} |",
          f"| 6. county centroids (report only) | mismatches={r6.get('n_mismatches', 'n/a')} |",
          f"| 7. land coverage | {r7['passed']} (stop={len(r7['stop_ge_100_km2'])}, report={len(r7['report_1_to_100_km2'])}) |",
          f"| 8. nested units (P8) | {r8['passed']} (max {r8['max_per_country']} per country) |",
          f"| 9. reconciliation with previous release | {r9['passed']}{' (skipped)' if r9.get('skipped') else ''} |",
          f"| 10. contested_areas | {r10['passed']} ({r10['n_zones']} zones) |",
          f"| 11. CLDR codes and names | {r11['passed']} (exceptions: {', '.join(e['unit_id'] for e in r11['exceptions']) or 'none'}) |",
          ""]
    (out_dir / "validation_report.md").write_text("\n".join(md), encoding="utf-8")

    log(f"validation_report.json / .md written to {out_dir}")
    log(f"OVERALL: {'PASSED' if overall_passed else 'FAILED'}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
