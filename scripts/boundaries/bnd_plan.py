#!/usr/bin/env python3
"""
bnd_plan.py -- v0.2.0 additions to the boundaries build (SPEC_BND_boundaries_v0_2_0.md r2, S2.1-S2.6).

Imported by build_boundaries.py and validate_boundaries.py. The France / Britain / USA /
Norway builders in build_boundaries.py are NOT touched; this module adds:

  - load_plan / build_plan_adm1 : one generic ADM1 builder driven by boundaries/adm1_plan.csv (S2.1)
  - apply_adm0_patches          : boundaries/adm0_patches.csv, Adjara into Georgia (S2.2)
  - apply_name_overrides        : boundaries/name_overrides.csv, applied to `name` at all levels (S2.4)
  - find_nested_units           : amendment P8 report (S2.1 p.6)
  - build_contested_areas       : layer `contested_areas` (S2.6)
  - land_coverage               : land-coverage check data (S2.3)
  - check_cldr                  : codes and English names against Unicode CLDR release-48-2 (S2.4a, r4)
  - reconcile_with_previous     : comparison against v0.1.0 unit_hashes.csv (S2.5)

Everything here uses the same precision-grid / make_valid discipline as bnd_common (bnd_common.clean).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

import bnd_common as c

# --- thresholds (SPEC v0.2.0) ---
LAND_STOP_KM2 = 100.0       # S2.3: uncovered land >= 100 km2 -> stop
LAND_REPORT_KM2 = 1.0       # S2.3: >= 1 km2 -> report
HOLE_MIN_AREA_KM2 = 0.01    # S2.2 p.2: interior rings smaller than this are removed from the Adjara addition
NESTED_STOP_COUNT = 5       # S2.1 p.6 / amendment P8: >= 5 nested units in a country -> stop
NESTED_MIN_SHARE = 0.99     # P8: share of the unit's boundary shared with one other unit of the same country
LOSS_REPORT_KM2 = 0.01      # clipping losses below this are not listed

PLAN_COLUMNS = ["iso3", "unit_id", "unit_code_iso", "name", "ne_adm1_codes", "method", "match_via", "cldr_code"]
ALLOWED_PLAN_METHODS = {"ne_as_is", "ne_dissolve"}
CONTESTED_COLUMNS = [
    "area_id", "frame_unit_ids", "name", "controlled_by", "claimed_by", "control_since", "label",
    "source_control", "source_claim", "checked_at", "checked_by",
]
CONTESTED_OUTPUT_FIELDS = ["area_id", "name", "controlled_by", "claimed_by", "control_since", "label"]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --------------------------------------------------------------------------
# S2.2 -- ADM0 patches (Adjara)
# --------------------------------------------------------------------------

def _drop_small_holes(geom, min_km2: float):
    """Remove interior rings smaller than min_km2. Returns (geometry, n_removed, removed_area_km2)."""
    n_removed, removed_area = 0, 0.0
    parts = []
    for part in c.explode_parts(geom):
        keep = []
        for ring in part.interiors:
            a = c.area_km2(shapely.Polygon(ring))
            if a < min_km2:
                n_removed += 1
                removed_area += a
            else:
                keep.append(ring)
        parts.append(shapely.Polygon(part.exterior, keep))
    return c.union_clean(parts), n_removed, removed_area


def apply_adm0_patches(adm0: gpd.GeoDataFrame, ne_adm1_wgs: gpd.GeoDataFrame, patches_path: Path,
                       logger: c.BuildLogger) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """S2.2: attach the geometry named by each row of adm0_patches.csv to its ADM0 unit.
    Only the rows of the file -- no 'nearest country' automation. Returns (patched adm0, report rows)."""
    adm0 = adm0.copy()
    report = []
    if not patches_path.exists():
        return adm0, report
    patches = _read_csv(patches_path)
    by_code = ne_adm1_wgs.set_index("adm1_code")
    for p in patches.itertuples():
        if p.iso3 not in set(adm0["unit_id"]):
            raise c.BuildError(f"adm0_patches.csv: iso3 {p.iso3!r} is not an ADM0 unit.")
        if not p.source.startswith("ne_10m_admin_1_states_provinces"):
            raise c.BuildError(f"adm0_patches.csv: unsupported source {p.source!r} for {p.iso3}.")
        if p.source_key not in by_code.index or isinstance(by_code.loc[p.source_key, "geometry"], gpd.GeoSeries):
            raise c.BuildError(f"adm0_patches.csv: source_key {p.source_key!r} not found exactly once in NE admin-1.")
        add = c.clean(by_code.loc[p.source_key, "geometry"])
        add_area = c.area_km2(add)
        idx = adm0.index[adm0["unit_id"] == p.iso3][0]
        before = adm0.at[idx, "geometry"]
        before_area, before_parts = c.area_km2(before), len(c.explode_parts(before))
        others = c.union_clean(adm0.loc[adm0["unit_id"] != p.iso3, "geometry"].values)
        overlap = c.area_km2(shapely.intersection(add, others))
        add = c.clean(shapely.difference(add, others))
        merged = c.union_clean([before, add])
        merged, n_holes, holes_area = _drop_small_holes(merged, HOLE_MIN_AREA_KM2)
        adm0.at[idx, "geometry"] = merged
        row = dict(
            iso3=p.iso3, source_key=p.source_key, expected_area_km2=float(p.area_km2),
            added_raw_km2=round(add_area, 1), removed_overlap_with_neighbours_km2=round(overlap, 4),
            removed_inner_rings=n_holes, removed_inner_rings_km2=round(holes_area, 4),
            area_before_km2=round(before_area, 1), area_after_km2=round(c.area_km2(merged), 1),
            parts_before=before_parts, parts_after=len(c.explode_parts(merged)),
        )
        if abs(add_area - float(p.area_km2)) > 0.05 * float(p.area_km2):
            raise c.BuildError(f"adm0_patches.csv: {p.iso3} addition is {add_area:.1f} km2, file says {p.area_km2}; stop and ask.")
        report.append(row)
        logger.add(step="adm0_patch", **row)
    return adm0, report


# --------------------------------------------------------------------------
# S2.1 -- generic ADM1 builder driven by adm1_plan.csv
# --------------------------------------------------------------------------

def load_plan(path: Path) -> pd.DataFrame:
    plan = _read_csv(path)
    missing = [k for k in PLAN_COLUMNS if k not in plan.columns]
    if missing:
        raise c.BuildError(f"{path}: columns missing: {missing}")
    if plan["unit_id"].duplicated().any():
        raise c.BuildError(f"{path}: duplicate unit_id: {plan['unit_id'][plan['unit_id'].duplicated()].tolist()[:10]}")
    bad = plan[~plan["method"].isin(ALLOWED_PLAN_METHODS)]
    if len(bad):
        raise c.BuildError(f"{path}: unknown method in {bad['unit_id'].tolist()[:10]}")
    return plan


def build_plan_adm1(plan: pd.DataFrame, ne_adm1_raw: gpd.GeoDataFrame, adm0: gpd.GeoDataFrame,
                    registry: pd.DataFrame, logger: c.BuildLogger):
    """S2.1. Returns (adm1 GeoDataFrame in the same column layout as the France/Britain/USA/Norway rows,
    loss rows for the report)."""
    ne = c.to_wgs84(ne_adm1_raw)
    ne = c.clean_geodataframe(ne)
    counts = ne["adm1_code"].value_counts()

    # every NE object used by the plan at most once, across all countries
    used: dict[str, str] = {}
    for r in plan.itertuples():
        for code in r.ne_adm1_codes.split(";"):
            code = code.strip()
            if code in used:
                raise c.BuildError(f"NE adm1_code {code} used twice in plan ({used[code]} and {r.unit_id}). Stop.")
            used[code] = r.unit_id
            if counts.get(code, 0) != 1:
                raise c.BuildError(f"NE adm1_code {code} ({r.unit_id}) found {counts.get(code, 0)} times in NE admin-1, expected exactly 1. Stop.")

    ne_geom = dict(zip(ne["adm1_code"], ne.geometry))
    adm0_geom = dict(zip(adm0["unit_id"], adm0.geometry))
    adm0_tree = shapely.STRtree(adm0.geometry.values)
    adm0_ids = adm0["unit_id"].values

    reg = registry[registry["level"] == "ADM1"].set_index("iso3") if registry is not None else None
    rows, losses = [], []
    for r in plan.itertuples():
        if r.iso3 not in adm0_geom:
            raise c.BuildError(f"{r.unit_id}: iso3 {r.iso3} is not an ADM0 unit.")
        codes = [x.strip() for x in r.ne_adm1_codes.split(";")]
        raw = c.union_clean([ne_geom[x] for x in codes])
        raw_area = c.area_km2(raw)
        geom = c.clean(shapely.intersection(raw, adm0_geom[r.iso3]))
        if geom is None or geom.is_empty:
            raise c.BuildError(f"{r.unit_id}: empty after clipping to ADM0 {r.iso3} (S2.1 p.4: for GEO-1-AJ this means the "
                               f"Adjara patch did not work). Stop.")
        lost_geom = c.clean(shapely.difference(raw, geom))
        lost = max(raw_area - c.area_km2(geom), 0.0)
        if lost >= LOSS_REPORT_KM2:
            where = []
            if lost_geom is not None and not lost_geom.is_empty:
                for j in adm0_tree.query(lost_geom, predicate="intersects"):
                    a = c.area_km2(shapely.intersection(lost_geom, adm0.geometry.values[int(j)]))
                    if a >= LOSS_REPORT_KM2 and adm0_ids[int(j)] != r.iso3:
                        where.append((adm0_ids[int(j)], a))
            where.sort(key=lambda t: -t[1])
            to_other = sum(a for _, a in where)
            losses.append(dict(
                unit_id=r.unit_id, iso3=r.iso3, area_raw_km2=round(raw_area, 2), area_kept_km2=round(c.area_km2(geom), 2),
                lost_km2=round(lost, 2), lost_share=round(lost / raw_area, 5) if raw_area else None,
                lost_to=";".join(f"{k}:{a:.2f}" for k, a in where) or "",
                lost_to_no_adm0_km2=round(max(lost - to_other, 0.0), 2),
            ))
        if reg is not None and r.iso3 in reg.index:
            ut_local, ut_en = reg.loc[r.iso3, "unit_type_local"], reg.loc[r.iso3, "unit_type_en"]
            published = str(reg.loc[r.iso3, "verified"]).lower() == "true"
        else:
            ut_local, ut_en, published = "", "", False
        rows.append(dict(
            unit_id=r.unit_id, iso3=r.iso3, level="ADM1", parent_id=r.iso3, name=r.name,
            unit_type_local=ut_local, unit_type_en=ut_en, method=r.method,
            source=f"Natural Earth {c.NE_VERSION}", source_vintage=c.NE_VERSION, license="public domain",
            boundary_vintage=c.NE_VERSION, src_ref=";".join(codes), published=published, geometry=geom,
        ))
    out = gpd.GeoDataFrame(rows, crs=c.CRS_WGS84)
    logger.add(step="build_plan_adm1", n_units=len(out), n_countries=int(out["iso3"].nunique()), n_losses=len(losses))
    return out, losses


# --------------------------------------------------------------------------
# S2.4 -- name overrides
# --------------------------------------------------------------------------

def apply_name_overrides(frames: dict[str, gpd.GeoDataFrame], path: Path, logger: c.BuildLogger):
    """Apply boundaries/name_overrides.csv to the `name` column of every level. `name_source` must equal the
    current value (otherwise the override is stale -> stop)."""
    if not path.exists():
        return frames, []
    ov = _read_csv(path)
    applied = []
    for r in ov.itertuples():
        hit = [lvl for lvl, g in frames.items() if (g["unit_id"] == r.unit_id).any()]
        if len(hit) != 1:
            raise c.BuildError(f"name_overrides.csv: {r.unit_id} found in {hit} (expected exactly one level).")
        g = frames[hit[0]]
        idx = g.index[g["unit_id"] == r.unit_id]
        if len(idx) != 1:
            raise c.BuildError(f"name_overrides.csv: {r.unit_id} not unique in {hit[0]}.")
        cur = g.at[idx[0], "name"]
        if cur != r.name_source:
            raise c.BuildError(f"name_overrides.csv: {r.unit_id}: current name {cur!r} != name_source {r.name_source!r}. Stop.")
        g.at[idx[0], "name"] = r.name
        applied.append(dict(unit_id=r.unit_id, level=hit[0], old=cur, new=r.name))
    logger.add(step="name_overrides", n_applied=len(applied), applied=applied)
    return frames, applied


# --------------------------------------------------------------------------
# S2.1 p.6 / P8 -- nested units
# --------------------------------------------------------------------------

def find_nested_units(adm1: gpd.GeoDataFrame, iso3_list: list[str] | None = None) -> list[dict]:
    """Amendment P8: a unit is nested (an enclave) when its whole outer boundary is shared with ONE other unit of the
    same country (it sits in a hole of that unit). Shared boundary share = length of the common boundary / length of the
    inner boundary (equal-area CRS, metres); nested if >= NESTED_MIN_SHARE."""
    rows = []
    for iso3, g in adm1.groupby("iso3"):
        if iso3_list is not None and iso3 not in iso3_list:
            continue
        if len(g) < 2:
            continue
        g = g.reset_index(drop=True)
        eq = c.to_equal_area(g.geometry)
        tree = shapely.STRtree(eq.values)
        for i, geom in enumerate(eq.values):
            if geom.is_empty:
                continue
            inner_b = geom.boundary
            L = inner_b.length
            if L <= 0:
                continue
            best = None
            for j in tree.query(geom, predicate="intersects"):
                j = int(j)
                if j == i:
                    continue
                shared = shapely.intersection(inner_b, eq.values[j].buffer(1.0)).length / L
                if best is None or shared > best[1]:
                    best = (j, shared)
            if best is not None and best[1] >= NESTED_MIN_SHARE:
                rows.append(dict(iso3=iso3, inner=g.at[i, "unit_id"], outer=g.at[best[0], "unit_id"],
                                 inner_km2=round(geom.area / 1e6, 2), shared_boundary_share=round(best[1], 4)))
    return rows


def check_nested(rows: list[dict]) -> dict:
    per = pd.Series([r["iso3"] for r in rows]).value_counts().to_dict() if rows else {}
    over = {k: v for k, v in per.items() if v >= NESTED_STOP_COUNT}
    return dict(passed=not over, per_country=per, max_per_country=max(per.values()) if per else 0, rows=rows, over_limit=over)


# --------------------------------------------------------------------------
# S2.3 -- land coverage
# --------------------------------------------------------------------------

def land_coverage(ne_adm1_raw: gpd.GeoDataFrame, adm0: gpd.GeoDataFrame, whitelist_path: Path | None) -> dict:
    """Area of each NE admin-1 object not covered by the union of ADM0 (minus whitelisted holes)."""
    ne = c.clean_geodataframe(c.to_wgs84(ne_adm1_raw))
    cover = c.union_clean(adm0.geometry.values)
    if whitelist_path is not None and Path(whitelist_path).exists():
        wl = gpd.read_file(whitelist_path)
        wl_union = c.union_clean(wl.geometry.values) if len(wl) else None
        # a whitelisted hole is not land that ADM0 has "lost" -- remove it from the reference, not from ADM0
    else:
        wl_union = None
    tree = shapely.STRtree(ne.geometry.values)
    rows = []
    for i, geom in enumerate(ne.geometry.values):
        unc = c.clean(shapely.difference(geom, cover))
        if unc is None or unc.is_empty:
            continue
        if wl_union is not None:
            unc = c.clean(shapely.difference(unc, wl_union))
        a = c.area_km2(unc)
        if a >= 0.001:
            r = ne.iloc[i]
            rows.append(dict(adm1_code=r["adm1_code"], name=r.get("name"), adm0_a3=r.get("adm0_a3"),
                             iso_3166_2=r.get("iso_3166_2"), area_km2=round(a, 2),
                             lon=round(unc.centroid.x, 3), lat=round(unc.centroid.y, 3)))
    rows.sort(key=lambda t: -t["area_km2"])
    stop = [r for r in rows if r["area_km2"] >= LAND_STOP_KM2]
    report = [r for r in rows if LAND_REPORT_KM2 <= r["area_km2"] < LAND_STOP_KM2]
    return dict(passed=not stop, n_ne_objects=len(ne), stop_ge_100_km2=stop, report_1_to_100_km2=report,
                n_below_1_km2=len([r for r in rows if r["area_km2"] < LAND_REPORT_KM2]))


# --------------------------------------------------------------------------
# S2.6 -- contested_areas
# --------------------------------------------------------------------------

def build_contested_areas(path: Path, frame_by_id: dict[str, object], adm0_ids: set[str]):
    """Reads boundaries/contested_areas.csv (written by [RES6]; this code never edits it). Geometry = union of the
    already-built frame units named in frame_unit_ids. Returns (GeoDataFrame, problems). Empty file -> empty layer."""
    cols = CONTESTED_OUTPUT_FIELDS
    if not path.exists():
        return gpd.GeoDataFrame({k: [] for k in cols}, geometry=[], crs=c.CRS_WGS84), [], 0
    df = _read_csv(path)
    missing = [k for k in CONTESTED_COLUMNS if k not in df.columns]
    if missing:
        raise c.BuildError(f"{path}: columns missing: {missing}")
    problems = []
    rows = []
    if df["area_id"].duplicated().any():
        problems.append("duplicate area_id")
    for r in df.itertuples():
        ids = [x.strip() for x in r.frame_unit_ids.split(";") if x.strip()]
        absent = [x for x in ids if x not in frame_by_id]
        if not ids or absent:
            problems.append(f"{r.area_id}: frame_unit_ids not in the build: {absent or 'empty'}")
            continue
        for fld in ("controlled_by", "claimed_by"):
            bad = [x for x in getattr(r, fld).split(";") if x.strip() and x.strip() not in adm0_ids]
            if bad or not getattr(r, fld).strip():
                problems.append(f"{r.area_id}: {fld} not ADM0 unit(s): {bad or 'empty'}")
        for fld in ("name", "label"):
            txt = getattr(r, fld)
            if not txt.isascii():
                problems.append(f"{r.area_id}: {fld} is not English/ASCII (G7)")
        geom = c.union_clean([frame_by_id[x] for x in ids])
        rows.append(dict(area_id=r.area_id, name=r.name, controlled_by=r.controlled_by, claimed_by=r.claimed_by,
                         control_since=r.control_since, label=r.label, geometry=geom))
    gdf = gpd.GeoDataFrame(rows, crs=c.CRS_WGS84) if rows else gpd.GeoDataFrame({k: [] for k in cols}, geometry=[], crs=c.CRS_WGS84)
    if len(gdf) > 1:
        for o in c.pairwise_overlaps(gdf.assign(unit_id=gdf["area_id"])):
            problems.append(f"zones overlap: {o}")
    return gdf, problems, len(df)


# --------------------------------------------------------------------------
# S2.4a -- codes and names against Unicode CLDR release-48-2
# --------------------------------------------------------------------------

def _cldr_files(manifest: dict) -> dict[str, Path]:
    need = {"cldr_subdivisions_en": "en.xml", "cldr_subdivisions": "subdivisions.xml",
            "cldr_supplemental_metadata": "supplementalMetadata.xml"}
    out = {}
    for k in need:
        if k not in manifest:
            raise c.BuildError(f"sources_manifest.json has no {k!r} -- run fetch_boundary_sources.py (SPEC v0.2.0 S1).")
        out[k] = Path(manifest[k]["path"])
    return out


def check_cldr(plan: pd.DataFrame, unit_names: dict[str, str], manifest: dict) -> dict:
    """S2.4a. For every row of adm1_plan.csv, after name_overrides:
    1. cldr_code is in the containment tree of subdivisions.xml under its own country;
    2. the suffix of unit_id = cldr_code without its first two letters, upper case;
    3. name (the built unit's name) = the name of cldr_code in en.xml, whatever its draft status.
    One allowed exception to 3: no name in en.xml and supplementalMetadata.xml has a subdivisionAlias with
    reason="overlong" for the code -> the plan's name stays, listed in `exceptions`."""
    import xml.etree.ElementTree as ET
    files = _cldr_files(manifest)
    tree = ET.parse(files["cldr_subdivisions"]).getroot()
    contains = {}
    for sg in tree.iter("subgroup"):
        contains.setdefault(sg.get("type"), set()).update(sg.get("contains", "").split())
    def reach(root: str) -> set[str]:
        seen, stack = set(), list(contains.get(root, ()))
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(contains.get(x, ()))
        return seen
    reach_cache: dict[str, set[str]] = {}
    names: dict[str, list[tuple[str, str]]] = {}
    for sd in ET.parse(files["cldr_subdivisions_en"]).getroot().iter("subdivision"):
        names.setdefault(sd.get("type"), []).append((sd.get("alt", ""), (sd.text or "").strip()))
    overlong = {a.get("type"): a.get("replacement") for a in
                ET.parse(files["cldr_supplemental_metadata"]).getroot().iter("subdivisionAlias")
                if a.get("reason") == "overlong"}
    viol, exceptions = [], []
    for r in plan.itertuples():
        code = r.cldr_code
        cc = code[:2].upper()
        if cc not in reach_cache:
            reach_cache[cc] = reach(cc)
        if code not in reach_cache[cc]:
            viol.append((r.unit_id, "p1_code_not_in_tree_under_country", code))
        if r.unit_id.rsplit("-", 1)[-1] != code[2:].upper():
            viol.append((r.unit_id, "p2_suffix_differs_from_code", code))
        if r.unit_id not in unit_names:
            viol.append((r.unit_id, "unit_missing_in_build", code))
            continue
        built = unit_names[r.unit_id]
        cand = [t for alt, t in names.get(code, []) if alt == ""]
        if not cand:
            if code in overlong:
                exceptions.append(dict(unit_id=r.unit_id, cldr_code=code, name=built, replacement=overlong[code],
                                       note="no name in en.xml; code replaced by the region code (reason=overlong); plan name kept"))
            else:
                viol.append((r.unit_id, "p3_no_name_in_en_xml", code))
        elif len(set(cand)) != 1 or cand[0] != built:
            viol.append((r.unit_id, "p3_name_differs", f"built={built!r} en.xml={cand!r}"))
    return dict(passed=not viol, n_checked=len(plan), violations=viol[:100], n_violations=len(viol), exceptions=exceptions)


# --------------------------------------------------------------------------
# S2.5 -- reconciliation with the previous release
# --------------------------------------------------------------------------

def reconcile_with_previous(prev_path: Path, new_path: Path, expected_geom_changed: set[str],
                            name_override_ids: set[str], plan_iso3: set[str]) -> dict:
    prev = pd.read_csv(prev_path, dtype=str).set_index("unit_id")
    new = pd.read_csv(new_path, dtype=str).set_index("unit_id")
    missing = sorted(set(prev.index) - set(new.index))
    added = sorted(set(new.index) - set(prev.index))
    common = prev.index.intersection(new.index)
    geom_changed = sorted(u for u in common if prev.at[u, "geom_sha256_16"] != new.at[u, "geom_sha256_16"])
    attr_changed = sorted(u for u in common if prev.at[u, "attr_sha256_16"] != new.at[u, "attr_sha256_16"])
    problems = []
    if missing:
        problems.append(f"{len(missing)} unit_id of the previous release are missing: {missing[:10]}")
    if set(geom_changed) != expected_geom_changed:
        problems.append(f"geometry changed for {geom_changed[:20]} (n={len(geom_changed)}), expected exactly {sorted(expected_geom_changed)}")
    name_override_ids = {u for u in name_override_ids if u in prev.index}  # overrides of NEW units (CHN-1-NM) are not changes
    if set(attr_changed) != name_override_ids:
        problems.append(f"attributes changed for {sorted(set(attr_changed) ^ name_override_ids)[:20]} "
                        f"(unexpected or missing), expected exactly the name_overrides ids")
    return dict(passed=not problems, problems=problems, n_prev=len(prev), n_new=len(new), n_missing=len(missing),
                n_added=len(added), geom_changed=geom_changed, attr_changed=attr_changed, added_ids_sample=added[:5])
