r"""
build_adm1_transmission_hifld.py
================================
SPEC_USA_states_v0_2_0 r5, section 2.5 (0.2.0) and SPEC_USA_AKHI_v0_3_0 r2 (0.3.0):
transmission lines by state (HIFLD).

The source has no state field, so the state is made from the same cut of line segments by county
that builds the county layer (overlay, EPSG:5070): every fragment lies in one county, so a line
through several counties is not counted twice. State km per voltage class = sum of the UNROUNDED
fragment lengths of the state's counties, rounded to whole km once. The county layer is recomputed
with the rule of build_layer_transmission_lines_hifld.py (COPY OF, marked) and the 3,109 contiguous
counties are compared with the CSV of release 0.1.0. Any difference stops the build. The 49
contiguous state rows are also compared with the 0.2.0 build.

--states all (default): Alaska and Hawaii are added (EPSG:5070 for every state, SPEC r2 4a item 1).
  - the lines are the lines of the 0.2.0 frame (the rectangle of the contiguous counties, the rule
    of the old builder, unchanged) plus the lines that intersect an Alaska or Hawaii county;
  - the segment layer (GeoJSON of all these lines) is written; its first part must equal the segment
    file of 0.1.0 value for value (ID, STATUS, OWNER, voltage, class, geometry), the added lines are
    counted by state (expected 165 + 184 = 349).
--states contiguous reproduces the 0.2.0 build (no segment file is written).

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_transmission_hifld.py --snapshot-date 20261109

It cuts about 94,000 lines by 3,144 counties: the 0.2.0 cut took 6.5 s, expect under a minute; reading
the previous segment file for the comparison takes about a minute more.
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import
from adm1_common import check, log
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

LAYER = "transmission_hifld"
LAYER_ID = "energy_transmission_hifld_adm1"
DEFAULT_SHP = (r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001"
               r"\Electric_Power_Transmission_Lines_A.shp")
ALLOWED_STATUSES = {"IN SERVICE", "NOT AVAILABLE"}  # COPY OF build_layer_transmission_lines_hifld.py
VOLTAGE_CLASS_BOUNDARIES = [(765, "ge765"), (500, "v500"), (345, "v345"), (230, "v230"),
                            (138, "v138"), (115, "v115"), (69, "v69")]
LEGACY_META = "layer_transmission_lines_hifld_meta.json"
LEGACY_TABLE = "layer_transmission_lines_hifld_20260913.csv"
LEGACY_SEGMENTS = "layer_transmission_lines_hifld_segments_20260913.geojson"
SEG_COLS = ["ID", "STATUS", "voltage_kv", "voltage_class", "OWNER", "geometry"]  # COPY OF cols_raw

KM_TOTAL_EXPECTED = 942549          # sum of the county CSVs of release 0.1.0, 49 states
SEGMENTS_ADDED_EXPECTED = 349       # Alaska 165 + Hawaii 184 (pre-flight 08.11.2026)
SEGMENTS_IN_FRAME = 93880           # the 0.2.0 report
OUTSIDE_COUNTY_KM_FRAME = 1444.6    # frame lines in no county, 0.2.0 report (contiguous counties only)
# Alaska, Hawaii (pre-flight 08.11.2026, section 9 item 4): added segments, km_total in counties (EPSG:5070),
# max voltage, counties without any line
EXPECTED_AKHI = {"02": {"name": "Alaska", "segments": 165, "km_total": 2812, "max_kv": 230.0, "no_line": 16, "counties": 30},
                 "15": {"name": "Hawaii", "segments": 184, "km_total": 1250, "max_kv": 138.0, "no_line": 1, "counties": 5}}
KM_TOL_AKHI = 6  # "about" figures of the pre-flight; the state value is rounded once per class


def classify_voltage(v) -> str:
    """COPY OF build_layer_transmission_lines_hifld.py."""
    if v is None:
        return "lt69_unknown"
    for threshold, label in VOLTAGE_CLASS_BOUNDARIES:
        if v >= threshold:
            return label
    return "lt69_unknown"  # also NaN and v < 69


def state_km_tables(clipped: pd.DataFrame, km_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """State km per class from UNROUNDED fragment lengths, rounded once (SPEC 2.5).

    clipped: columns fips, voltage_class, length_km (one row per fragment).
    Returns (unrounded sums, rounded ints), both indexed by state FIPS, columns = km_cols.
    """
    c = clipped.assign(state_fips=clipped["fips"].str[:2])
    unr = c.groupby(["state_fips", "voltage_class"])["length_km"].sum().unstack(fill_value=0.0)
    unr.columns = [f"km_{x}" for x in unr.columns]
    unr = unr.reindex(columns=km_cols, fill_value=0.0)
    rounded = unr.round(0).astype(int)
    return unr, rounded


def compare_segments(new_path: Path, old_path: Path, in_frame: np.ndarray, snap: str) -> dict:
    """The lines of the 0.2.0 frame in the NEW segment file must equal the OLD segment file (0.1.0)
    value for value: same IDs in the same order, STATUS, OWNER, voltage_kv, voltage_class, geometry.
    Both files are read from disk (both written by the same code path); any difference stops."""
    import geopandas as gpd

    log.info("Reading both segment files for the comparison (about a minute)...")
    new = gpd.read_file(new_path)
    old = gpd.read_file(old_path)
    nf = new[in_frame].reset_index(drop=True)
    problems: list[str] = []
    if len(nf) != len(old):
        problems.append(f"row counts differ: frame part of the new file {len(nf)}, old file {len(old)}")
    else:
        for c in ("ID", "STATUS", "OWNER", "voltage_class"):
            bad = nf[c].astype(str).values != old[c].astype(str).values
            if bad.any():
                ex = [(i, nf.loc[i, c], old.loc[i, c]) for i in np.flatnonzero(bad)[:6]]
                problems.append(f"{c}: {int(bad.sum())} rows differ (row, new, old): {ex}")
        x = pd.to_numeric(nf["voltage_kv"], errors="coerce").astype("float64")
        y = pd.to_numeric(old["voltage_kv"], errors="coerce").astype("float64")
        bad = (x.isna() != y.isna()) | (x.notna() & y.notna() & (x != y))
        if bad.any():
            problems.append(f"voltage_kv: {int(bad.sum())} rows differ, first {list(np.flatnonzero(bad.values)[:6])}")
        same_geom = nf.geometry.geom_equals_exact(old.geometry, tolerance=1e-9)
        if not same_geom.all():
            problems.append(f"geometry: {int((~same_geom).sum())} rows differ, first {list(np.flatnonzero(~same_geom.values)[:6])}")
    if problems:
        C._stop_with(problems, f"adm1_identity_FAIL_segments_{snap}.txt", "SEGMENT FILE IDENTITY WITH 0.1.0 FAILED")
    new_ids = new["ID"].astype(str)
    extra_ids = new_ids[~in_frame]
    dup = int(new_ids.duplicated().sum())
    log.info("Segments: %d old rows equal value for value; %d added; duplicated IDs in the new file: %d",
             len(old), int((~in_frame).sum()), dup)
    return {"status": "OK", "old_file": old_path.name, "old_rows": int(len(old)), "new_rows": int(len(new)),
            "added_rows": int(len(extra_ids)), "duplicated_ids_in_new_file": dup,
            "compared": ["ID", "STATUS", "OWNER", "voltage_kv", "voltage_class", "geometry (exact to 1e-9 degrees)"]}


def main() -> None:
    import geopandas as gpd
    from shapely.geometry import box

    ap = C.base_parser("ADM1 builder: transmission lines, HIFLD (state from the county cut)")
    ap.add_argument("--shp", default=DEFAULT_SHP)
    ap.add_argument("--prev-segments", default=str(C.OUTPUT_DIR / LEGACY_SEGMENTS),
                    help="segment file of 0.1.0 (default: %(default)s); needed with --states all")
    args = ap.parse_args()
    snap, scope = args.snapshot_date, C.make_scope(args.states)
    shp = Path(args.shp)
    n_cov = scope.n_states
    log.info("--states %s: %d states, %d counties", scope.mode, n_cov, scope.n_counties)
    prev_seg = Path(args.prev_segments)
    if scope.mode == "all" and not prev_seg.exists():
        raise SystemExit(f"STOP: the segment file of 0.1.0 is needed to prove the old segments unchanged: {prev_seg}")

    input_paths = {**C.shp_files(shp, "hifld_lines"), **C.shp_files(C.BOUNDARY_SHP, "county_shp")}
    if scope.mode == "all":
        input_paths["segments_0_1_0_geojson"] = prev_seg
    inputs = C.hash_inputs(input_paths)

    log.info("Reading HIFLD lines...")
    gdf = gpd.read_file(shp)
    n_all = len(gdf)
    # ---- COPY OF build_layer_transmission_lines_hifld.py (county rule) -------------------------
    gdf = gdf[gdf["STATUS"].isin(ALLOWED_STATUSES)].copy()
    voltage_raw = pd.to_numeric(gdf["VOLTAGE"], errors="coerce")
    gdf["voltage_kv"] = voltage_raw.where(voltage_raw > 0)  # sentinel -999999 -> NaN
    gdf["voltage_class"] = gdf["voltage_kv"].apply(classify_voltage)
    gdf = gdf.to_crs(C.JOIN_CRS)
    # the frame of the old builder: rectangle of the CONTIGUOUS counties (in 5070); with --states all the counties
    # of Alaska and Hawaii are loaded too, but the rectangle is still made from the contiguous ones
    counties = C.load_counties(scope)
    contig = counties[counties["STATEFP"].isin(C.CONUS_STATES_FIPS)]
    minx, miny, maxx, maxy = contig.total_bounds
    in_frame_all = gdf.geometry.intersects(box(minx, miny, maxx, maxy))
    gdf_frame = gdf[in_frame_all].copy()
    # ---- end of the copied frame rule --------------------------------------------------------------
    n_frame = len(gdf_frame)

    extra_by_state: dict[str, int] = {}
    if scope.mode == "all":
        akhi_c = counties[~counties["STATEFP"].isin(C.CONUS_STATES_FIPS)]
        cand = gdf[~in_frame_all]
        hit = gpd.sjoin(cand[["geometry"]], akhi_c[["STATEFP", "geometry"]], how="inner", predicate="intersects")
        extra_idx = hit.index.unique()
        per_line_state = hit.groupby(level=0)["STATEFP"].agg(lambda s: ",".join(sorted(set(s))))
        extra_by_state = per_line_state.value_counts().to_dict()
        log.info("Lines outside the old frame that intersect an Alaska or Hawaii county: %d %s",
                 len(extra_idx), extra_by_state)
        keep = in_frame_all | gdf.index.isin(extra_idx)  # original file order kept
        gdf_conus = gdf[keep].copy()
        in_frame_flag = in_frame_all[keep].values.astype(bool)
    else:
        gdf_conus = gdf_frame
        in_frame_flag = np.ones(len(gdf_conus), dtype=bool)

    # ---- COPY OF build_layer_transmission_lines_hifld.py (county rule), continued -------------------
    joined = gpd.sjoin(gdf_conus[["voltage_kv", "geometry"]], counties[["fips", "geometry"]],
                       how="inner", predicate="intersects")
    has_any_line_fips = set(joined["fips"].unique())
    max_v = joined.groupby("fips")["voltage_kv"].max().rename("max_voltage_kv")
    log.info("overlay (geometric cut) - may take a minute...")
    t0 = dt.datetime.now()
    clipped = gpd.overlay(gdf_conus[["voltage_class", "geometry"]], counties[["fips", "geometry"]],
                          how="intersection")
    log.info("overlay done in %.1f s, %d fragments", (dt.datetime.now() - t0).total_seconds(), len(clipped))
    clipped["length_km"] = clipped.geometry.length / 1000.0
    by_class = clipped.groupby(["fips", "voltage_class"])["length_km"].sum().round(0).astype(int)
    km_wide = by_class.unstack(fill_value=0)
    km_wide.columns = [f"km_{c}" for c in km_wide.columns]
    result = counties.merge(max_v, on="fips", how="left").merge(km_wide, on="fips", how="left")
    km_cols_rule = [c for c in result.columns if c.startswith("km_")]
    result[km_cols_rule] = result[km_cols_rule].fillna(0).astype(int)
    result["has_any_line"] = result["fips"].isin(has_any_line_fips)
    total_km = result[km_cols_rule].sum(axis=1)
    unknown_km = result["km_lt69_unknown"] if "km_lt69_unknown" in result.columns else 0
    result["frac_km_unknown_voltage"] = (unknown_km / total_km).where(total_km > 0)
    # ---- end of COPY ----------------------------------------------------------------------------
    rec = result.set_index("fips")
    rec["coverage_status"] = "covered"

    release = C.read_release("energy_transmission_hifld_adm2.csv")
    rel_km = [c for c in release.columns if c.startswith("km_") and c != "km_total"]
    if set(km_cols_rule) - set(rel_km):
        raise SystemExit(f"STOP: classes {sorted(set(km_cols_rule) - set(rel_km))} not in the release 0.1.0 CSV")
    identity = C.compare_county(
        LAYER, snap, rec, release,
        exact_cols=rel_km, float_cols=["max_voltage_kv", "frac_km_unknown_voltage"], bool_cols=["has_any_line"])

    # ---- segment file (--states all): the old part equals 0.1.0 value for value ---------------------
    segments_info = None
    if scope.mode == "all":
        seg_path = C.OUTPUT_DIR / f"layer_transmission_lines_hifld_segments_{snap}.geojson"
        log.info("Writing the segment file (%d lines)...", len(gdf_conus))
        gdf_conus[SEG_COLS].to_crs(C.STORAGE_CRS).to_file(seg_path, driver="GeoJSON")
        segments_info = compare_segments(seg_path, prev_seg, in_frame_flag, snap)
        segments_info.update({"file": seg_path.name, "sha256": C.sha256_file(seg_path),
                              "added_by_state_fips": {k: int(v) for k, v in extra_by_state.items()}})

    # ---- state values (SPEC 2.5) -----------------------------------------------------------------
    unr, rounded = state_km_tables(clipped[["fips", "voltage_class", "length_km"]], rel_km)
    rounded["km_total"] = rounded[rel_km].sum(axis=1)
    rec_state = rec.copy()
    rec_state["state_fips"] = rec_state.index.str[:2]
    gs = rec_state.groupby("state_fips")
    st = rounded.copy()
    st["max_voltage_kv"] = gs["max_voltage_kv"].max()
    st["has_any_line"] = gs["has_any_line"].any()
    st["frac_km_unknown_voltage"] = (st["km_lt69_unknown"] / st["km_total"]).where(st["km_total"] > 0)
    covered = C.state_units(scope.fips).query("covered")["state_fips"]
    st = st.reindex(covered)
    if st[rel_km + ["km_total"]].isna().any().any():
        raise SystemExit("STOP: a covered state has no line fragments")
    st[rel_km + ["km_total"]] = st[rel_km + ["km_total"]].astype(int)
    st["frac_km_unknown_voltage"] = st["frac_km_unknown_voltage"].round(6)

    value_cols = ["max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"] + rel_km + ["km_total"]
    out = C.build_state_frame(st, value_cols, int_cols=rel_km + ["km_total"], bool_cols=["has_any_line"],
                              nullable_cols=["max_voltage_kv", "frac_km_unknown_voltage"], covered_fips=scope.fips)
    identity_state = C.compare_state_prev(
        LAYER, snap, out, args.prev_date, exact_cols=rel_km + ["km_total"],
        float_cols=["max_voltage_kv", "frac_km_unknown_voltage"], bool_cols=["has_any_line"])

    # ---- checks and reconciliation ---------------------------------------------------------------
    rec_ref = rec.copy()
    rec_ref["km_total"] = rec_ref[rel_km].sum(axis=1)  # the county table has no km_total; the yaml derives it
    ref_cols = rel_km + ["km_total", "max_voltage_kv", "has_any_line"]
    ref = C.combined_reference(release, rec_ref, ref_cols)
    n_cnty = rec_state.groupby("state_fips").size()
    problems = []
    recon_parts = []
    for col in rel_km + ["km_total"]:
        cs = C.county_sums_by_state(ref, col, scope.fips)
        tol_per = 0.5 if col != "km_total" else 0.5 * len(rel_km)
        part = C.reconcile(LAYER_ID, col, "km", st[col].astype(float), cs, [])
        part["rounding_tolerance_km"] = [tol_per * int(n_cnty.get(s, 0)) for s in st.index]
        part["within_tolerance"] = part["difference"].abs() <= part["rounding_tolerance_km"] + 1e-9
        part["state_unrounded_km"] = (unr[col].reindex(st.index).round(6).values if col in unr.columns
                                      else unr[rel_km].sum(axis=1).reindex(st.index).round(6).values)
        part["residual"] = part["difference"]  # no categories: the whole difference is rounding
        part["detail"] = "difference = state (rounded once) minus sum of rounded county km: rounding only"
        recon_parts.append(part)
        bad = part[~part["within_tolerance"]]
        if len(bad):
            problems.append(f"{col}: {len(bad)} states outside rounding tolerance: {list(bad['unit_id'])[:8]}")
    recon = pd.concat(recon_parts, ignore_index=True)

    # max voltage and has_any_line of the state vs its counties (release values; Alaska and Hawaii: this run)
    rel_c = ref[ref["fips"].notna()].copy()
    rel_c["state_fips"] = rel_c["fips"].str[:2]
    rel_max = pd.to_numeric(rel_c["max_voltage_kv"], errors="coerce").groupby(rel_c["state_fips"]).max()
    rel_has = rel_c["has_any_line"].map(lambda v: str(v).strip().lower() == "true").groupby(rel_c["state_fips"]).any()
    mv_bad = [s for s in st.index
              if not ((pd.isna(st.loc[s, "max_voltage_kv"]) and pd.isna(rel_max.get(s)))
                      or st.loc[s, "max_voltage_kv"] == rel_max.get(s))]
    has_bad = [s for s in st.index if bool(st.loc[s, "has_any_line"]) != bool(rel_has.get(s, False))]
    if problems or mv_bad or has_bad:
        raise SystemExit(f"STOP: checks failed: {problems}; max_voltage_kv differs {mv_bad}; has_any_line differs {has_bad}")

    # lines of the old frame in no county of the contiguous states (over water beyond the cb 500k coastline);
    # lines added for Alaska and Hawaii in no county of theirs
    clipped_conus = clipped[clipped["fips"].str[:2].isin(C.CONUS_STATES_FIPS)]
    total_len_km = float(gdf_frame.geometry.length.sum() / 1000.0)
    in_county_km = float(clipped_conus["length_km"].sum())
    outside_km = total_len_km - in_county_km
    akhi_outside = {}
    if scope.mode == "all":
        extra_lines = gdf_conus[~in_frame_flag]
        for f in C.AKHI_FIPS:
            ids = hit.index[hit["STATEFP"] == f].unique()
            tl = float(extra_lines.loc[extra_lines.index.isin(ids)].geometry.length.sum() / 1000.0)
            ic = float(clipped.loc[clipped["fips"].str[:2] == f, "length_km"].sum())
            akhi_outside[f] = {"lines_km": round(tl, 1), "in_counties_km": round(ic, 1), "in_no_county_km": round(tl - ic, 1)}

    km_sum_states = int(st["km_total"].sum())
    checks = [
        check("units: covered / not_covered", f"{n_cov} / {51 - n_cov}", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check("HIFLD records read / after STATUS filter / in the 0.2.0 frame", "94619 / - / -",
              f"{n_all} / {len(gdf)} / {n_frame}"),
        check("lines in the 0.2.0 frame", SEGMENTS_IN_FRAME, n_frame),
        check("frame lines in no contiguous county, km", OUTSIDE_COUNTY_KM_FRAME, round(outside_km, 1), tol=0.1),
        check("km_total, sum of the 49 contiguous states (km)", KM_TOTAL_EXPECTED,
              int(st.loc[st.index.isin(C.CONUS_STATES_FIPS), "km_total"].sum()),
              tol=49 * 0.5 * len(rel_km), note="expected ~942,549 within rounding"),
        check("km_total, sum of county CSVs (release 0.1.0)", KM_TOTAL_EXPECTED,
              int(C.county_sums_by_state(release, "km_total").sum())),
        check("class sums vs sum of county CSVs, states outside rounding tolerance", 0, 0),
        check("max_voltage_kv of a state = max of its counties, states that differ", 0, len(mv_bad)),
        check("has_any_line of a state = any of its counties, states that differ", 0, len(has_bad)),
        check("states with has_any_line = True", n_cov, int(pd.Series(st["has_any_line"]).sum())),
    ]
    if scope.mode == "all":
        akhi_no_line = {f: int((~rec.loc[rec.index.str[:2] == f, "has_any_line"]).sum()) for f in C.AKHI_FIPS}
        checks += [check("lines added to the segment file (Alaska + Hawaii)", SEGMENTS_ADDED_EXPECTED,
                         int(sum(extra_by_state.values())))]
        for f, e in EXPECTED_AKHI.items():
            checks += [
                check(f"{e['name']}: segments added", e["segments"], int(extra_by_state.get(f, 0))),
                check(f"{e['name']}: km_total in counties (EPSG:5070)", e["km_total"], int(st.loc[f, "km_total"]), tol=KM_TOL_AKHI),
                check(f"{e['name']}: max_voltage_kv", e["max_kv"], float(st.loc[f, "max_voltage_kv"])),
                check(f"{e['name']}: counties without any line (has_any_line false) / counties", f"{e['no_line']} / {e['counties']}",
                      f"{akhi_no_line[f]} / {int((rec.index.str[:2] == f).sum())}"),
            ]
            checks[-1]["ok"] = (akhi_no_line[f] == e["no_line"]) and int((rec.index.str[:2] == f).sum()) == e["counties"]
        checks += C.additivity_checks(out, args.prev_date, LAYER, rel_km + ["km_total"], tol=0.0)
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "states": scope.mode, "identity": identity,
        "identity_state_prev": identity_state, "checks": checks,
        "numbers": {
            "segments_read": n_all, "segments_after_status_filter": int(len(gdf)),
            "segments_in_frame_0_2_0": int(n_frame), "segments_in_file": int(len(gdf_conus)),
            "fragments_after_cut": int(len(clipped)),
            "length_in_frame_km": round(total_len_km, 1), "length_in_contiguous_counties_km": round(in_county_km, 1),
            "length_in_no_county_km": round(outside_km, 1),
            "akhi_lines_and_length_km": akhi_outside,
            "km_total_sum_states": km_sum_states,
            "km_total_sum_county_csv": int(C.county_sums_by_state(release, "km_total").sum()),
            "max_abs_difference_km_by_class": {c: float(recon.loc[recon["field"] == c, "difference"].abs().max())
                                               for c in rel_km + ["km_total"]},
        },
        "lists": {},
        "inputs": inputs,
    }
    if segments_info:
        report["segments"] = segments_info

    cov_text = ("50 states + DC (the 51 units)" if scope.mode == "all"
                else "48 states + DC (the 49 units); Alaska and Hawaii not_covered")
    akhi_gap = (" Alaska and Hawaii are cut in EPSG:5070 like the other states: lengths there are not geodesic "
                "(pre-flight: about +0.5 % in Alaska, +0.1 % in Hawaii against the geodesic length; about +0.5 % "
                "or less for the contiguous states is the same kind of deviation)." if scope.mode == "all" else "")
    meta = {
        "source": "HIFLD Transmission Lines (nationwide feature class)",
        "source_url": "https://gii.dhs.gov/HIFLD",
        "vintage": "archive export 2026-02-26 (see the provenance report); SOURCEDATE/VAL_DATE up to 2024-09-26",
        "license": "public HIFLD/DHS data; terms of use questions: hifld@hq.dhs.gov",
        "coverage": cov_text,
        "rule": "segments with STATUS IN SERVICE or NOT AVAILABLE, cut by the county polygons (EPSG:5070); "
                "state km = sum of unrounded fragment lengths of the state's counties, rounded once; "
                "km_total = sum of the published class columns",
        "states_mode": scope.mode,
        "n_units_covered": n_cov, "n_units_not_covered": 51 - n_cov,
        "known_gaps": (
            f"Length is counted inside county polygons only: {outside_km:,.0f} km of segments in the contiguous frame "
            "lie in no county (over water beyond the cb 500k coastline, or across the border) and are in neither "
            "the county nor the state values. Km are rounded to whole km." + akhi_gap + " Factual draft; wording by [RES]7."
        ),
        "inputs": inputs, "boundary_file": str(C.BOUNDARY_SHP),
        "identity_with_release_0_1_0": identity, "identity_state_with_0_2_0": identity_state,
    }
    csv_path = C.write_layer_csv(LAYER, out, meta, snap)

    tbl = result[["fips", "NAME", "NAMELSAD", "max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"] + km_cols_rule]
    county_meta = C.read_legacy_meta(LEGACY_META)
    county_meta.update({
        "coverage": cov_text, "states_mode": scope.mode,
        "n_units_covered": int(len(gdf_conus)),
        "n_units_no_data": int((~result["has_any_line"]).sum()),
        "rebuilt_for": "abf-layers 0.3.0 (SPEC_USA_AKHI_v0_3_0 r2); county rule unchanged, EPSG:5070 for every state",
        "boundary_file": str(C.BOUNDARY_SHP), "boundary_file_sha256": inputs["county_shp.shp"]["sha256"],
        "identity_with_release_0_1_0": identity,
    })
    county_csv = C.write_county_table("transmission_lines_hifld", tbl, county_meta, snap)
    report["county_table"] = {"file": county_csv.name, "rows": int(len(tbl)),
                              "text_vs_legacy": C.compare_text_to_legacy(county_csv, C.OUTPUT_DIR / LEGACY_TABLE)}
    C.assert_inputs_unchanged(inputs, input_paths)
    C.write_part(LAYER, snap, report, recon)
    log.info("DONE. %s ; %s", csv_path, county_csv)
    C.stop_if_failed(checks, LAYER)


if __name__ == "__main__":
    main()
