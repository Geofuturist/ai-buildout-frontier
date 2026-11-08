r"""
build_adm1_transmission_hifld.py
================================
SPEC_USA_states_v0_2_0 r5, section 2.5: transmission lines by state (HIFLD).

The source has no state field, so the state is made from the same cut of line segments by county
that builds the county layer (overlay, EPSG:5070): every fragment lies in one county, so a line
through several counties is not counted twice. State km per voltage class = sum of the UNROUNDED
fragment lengths of the state's counties, rounded to whole km once. The county layer is recomputed
with the rule of build_layer_transmission_lines_hifld.py (COPY OF, marked) and compared with the
CSV of release 0.1.0. Any difference stops the build.

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_transmission_hifld.py --snapshot-date 20261101

It cuts about 90,000 lines by 3,109 counties: expect several minutes.
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
KM_TOTAL_EXPECTED = 942549


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


def main() -> None:
    import geopandas as gpd

    ap = C.base_parser("ADM1 builder: transmission lines, HIFLD (state from the county cut)")
    ap.add_argument("--shp", default=DEFAULT_SHP)
    args = ap.parse_args()
    snap = args.snapshot_date
    shp = Path(args.shp)

    input_paths = {**C.shp_files(shp, "hifld_lines"), **C.shp_files(C.BOUNDARY_SHP, "county_shp")}
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
    counties = C.load_conus_counties()
    from shapely.geometry import box
    minx, miny, maxx, maxy = counties.total_bounds
    gdf_conus = gdf[gdf.geometry.intersects(box(minx, miny, maxx, maxy))].copy()
    joined = gpd.sjoin(gdf_conus[["voltage_kv", "geometry"]], counties[["fips", "geometry"]],
                       how="inner", predicate="intersects")
    has_any_line_fips = set(joined["fips"].unique())
    max_v = joined.groupby("fips")["voltage_kv"].max().rename("max_voltage_kv")
    log.info("overlay (geometric cut) - may take several minutes...")
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
    covered = C.state_units().query("covered")["state_fips"]
    st = st.reindex(covered)
    if st[rel_km + ["km_total"]].isna().any().any():
        raise SystemExit("STOP: a covered state has no line fragments")
    st[rel_km + ["km_total"]] = st[rel_km + ["km_total"]].astype(int)
    st["frac_km_unknown_voltage"] = st["frac_km_unknown_voltage"].round(6)

    value_cols = ["max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"] + rel_km + ["km_total"]
    out = C.build_state_frame(st, value_cols, int_cols=rel_km + ["km_total"], bool_cols=["has_any_line"],
                              nullable_cols=["max_voltage_kv", "frac_km_unknown_voltage"])

    # ---- checks and reconciliation ---------------------------------------------------------------
    n_cnty = rec_state.groupby("state_fips").size()
    problems = []
    recon_parts = []
    for col in rel_km + ["km_total"]:
        cs = C.county_sums_by_state(release, col)
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

    # max voltage and has_any_line of the state vs its counties (release values)
    rel_c = release[release["fips"].notna() & release["fips"].str[:2].isin(C.CONUS_STATES_FIPS)].copy()
    rel_c["state_fips"] = rel_c["fips"].str[:2]
    rel_max = pd.to_numeric(rel_c["max_voltage_kv"], errors="coerce").groupby(rel_c["state_fips"]).max()
    rel_has = rel_c["has_any_line"].map(lambda v: str(v).strip().lower() == "true").groupby(rel_c["state_fips"]).any()
    mv_bad = [s for s in st.index
              if not ((pd.isna(st.loc[s, "max_voltage_kv"]) and pd.isna(rel_max.get(s)))
                      or st.loc[s, "max_voltage_kv"] == rel_max.get(s))]
    has_bad = [s for s in st.index if bool(st.loc[s, "has_any_line"]) != bool(rel_has.get(s, False))]
    if problems or mv_bad or has_bad:
        raise SystemExit(f"STOP: checks failed: {problems}; max_voltage_kv differs {mv_bad}; has_any_line differs {has_bad}")

    # segments in the CONUS frame that lie in no county (over water beyond the cb 500k coastline)
    total_len_km = float(gdf_conus.geometry.length.sum() / 1000.0)
    in_county_km = float(clipped["length_km"].sum())
    outside_km = total_len_km - in_county_km

    km_sum_states = int(st["km_total"].sum())
    checks = [
        check("units: covered / not_covered", "49 / 2", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check("HIFLD records read / after STATUS filter / in CONUS frame", "94619 / - / -",
              f"{n_all} / {len(gdf)} / {len(gdf_conus)}"),
        check("km_total, sum of 49 states (km)", KM_TOTAL_EXPECTED, km_sum_states,
              tol=len(st) * 0.5 * len(rel_km), note="expected ~942,549 within rounding"),
        check("km_total, sum of county CSVs (release 0.1.0)", KM_TOTAL_EXPECTED,
              int(C.county_sums_by_state(release, "km_total").sum())),
        check("class sums vs sum of county CSVs, states outside rounding tolerance", 0, 0),
        check("max_voltage_kv of a state = max of its counties, states that differ", 0, len(mv_bad)),
        check("has_any_line of a state = any of its counties, states that differ", 0, len(has_bad)),
        check("states with has_any_line = True", 49, int(pd.Series(st["has_any_line"]).sum())),
    ]
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "identity": identity, "checks": checks,
        "numbers": {
            "segments_read": n_all, "segments_after_status_filter": int(len(gdf)),
            "segments_in_conus_frame": int(len(gdf_conus)), "fragments_after_cut": int(len(clipped)),
            "length_in_conus_frame_km": round(total_len_km, 1), "length_in_counties_km": round(in_county_km, 1),
            "length_in_no_county_km": round(outside_km, 1),
            "km_total_sum_states": km_sum_states,
            "km_total_sum_county_csv": int(C.county_sums_by_state(release, "km_total").sum()),
            "max_abs_difference_km_by_class": {c: float(recon.loc[recon["field"] == c, "difference"].abs().max())
                                               for c in rel_km + ["km_total"]},
        },
        "lists": {},
        "inputs": inputs,
    }
    meta = {
        "source": "HIFLD Transmission Lines (nationwide feature class)",
        "source_url": "https://gii.dhs.gov/HIFLD",
        "vintage": "archive export 2026-02-26 (see the provenance report); SOURCEDATE/VAL_DATE up to 2024-09-26",
        "license": "public HIFLD/DHS data; terms of use questions: hifld@hq.dhs.gov",
        "coverage": "48 states + DC (the 49 units); Alaska and Hawaii not_covered",
        "rule": "segments with STATUS IN SERVICE or NOT AVAILABLE, cut by the county polygons (EPSG:5070); "
                "state km = sum of unrounded fragment lengths of the state's counties, rounded once; "
                "km_total = sum of the published class columns",
        "n_units_covered": 49, "n_units_not_covered": 2,
        "known_gaps": (
            f"Length is counted inside county polygons only: {outside_km:,.0f} km of segments in the CONUS frame "
            "lie in no county (over water beyond the cb 500k coastline, or across the border) and are in neither "
            "the county nor the state values. Km are rounded to whole km. Factual draft; wording by [RES]7."
        ),
        "inputs": inputs, "boundary_file": str(C.BOUNDARY_SHP),
        "identity_with_release_0_1_0": identity,
    }
    csv_path = C.write_layer_csv(LAYER, out, meta, snap)
    C.assert_inputs_unchanged(inputs, input_paths)
    C.write_part(LAYER, snap, report, recon)
    log.info("DONE. %s", csv_path)


if __name__ == "__main__":
    main()
