r"""
build_adm1_generation_eia860.py
===============================
SPEC_USA_states_v0_2_0 r5, section 2.2 (0.2.0) and SPEC_USA_AKHI_v0_3_0 r2 (0.3.0):
generation by state (EIA-860, Operable, Status == 'OP').

State = field 'State' of the generator row (no coordinates needed), so offshore plants
fall into their states. In the same run the county layer is recomputed with the SAME rule
as build_layer_generation_eia860.py (copied below, marked "COPY OF") and the 3,109 contiguous
counties are compared with the CSV of release 0.1.0 (SPEC 2.1 item 5). Any difference stops
the build. The 49 contiguous state rows are also compared with the 0.2.0 build.

--states all (default) adds Alaska and Hawaii (EIA-860 covers both); --states contiguous
reproduces the 0.2.0 build.

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_generation_eia860.py --snapshot-date 20261109

Writes to data\conus\:
    layer_generation_eia860_adm1_<date>.csv, layer_generation_eia860_adm1_<date>_meta.json,
    layer_generation_eia860_<date>.csv + _meta.json   (county table of the release, legacy format),
    adm1_part_generation_eia860_<date>.json, adm1_recon_part_generation_eia860_<date>.csv
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import (sets the county-shp default)
from adm1_common import Cat, check, log
from pathlib import Path

import numpy as np
import pandas as pd

LAYER = "generation_eia860"
LAYER_ID = "energy_generation_eia860_adm1"
DEFAULT_INPUT_DIR = r"D:\GISData\Energy\USA\eia8602025"
BOUNDARY_FALLBACK_M = 1000.0  # COPY OF build_layer_generation_eia860.py
LEGACY_META = "layer_generation_eia860_20261009_meta.json"
LEGACY_TABLE = "layer_generation_eia860_20261009.csv"

# 49 contiguous units (0.2.0) and the totals with Alaska and Hawaii (pre-flight 08.11.2026, section 9 item 4)
EXPECTED = {
    "contiguous": {"mw_states": 1254379.4, "plants_states": 13593, "county_generators": 24957, "op_rows": 24961,
                   "state_generators": 24960},
    "all": {"mw_states": 1260035.3, "plants_states": 13807, "county_generators": 25655, "op_rows": 25659,
            "state_generators": 25658},
}
OFFSHORE_MW, OFFSHORE_PLANTS, OFFSHORE_GENERATORS = 171.3, 3, 3
CROSS_STATE_PLANTS = 22  # SPEC r6 2.8: accepted, rule "state by the field"
# Alaska and Hawaii: (generators, plants, MW)
EXPECTED_AKHI = {"02": (486, 141, 2220.5), "15": (212, 73, 3435.4)}


def _plant_table(sub: pd.DataFrame, key: str) -> pd.DataFrame:
    """One row per plant inside a category: name, state key, generators, MW."""
    return sub.groupby("Plant Code").agg(
        plant_name=("Plant Name", "first"), key=(key, "first"),
        n_gens=("Generator ID", "size"), mw=("mw", "sum"),
    )


def eia_categories(op: pd.DataFrame) -> tuple[dict[str, list[Cat]], dict[str, pd.DataFrame]]:
    """Reconciliation categories (SPEC 2.2).

    op needs: state_fips (state of the 'State' field), county_fips (county the generator
    landed in, NaN if none), has_coords (valid coordinates), mw, 'Generator ID', 'Plant Code',
    'Plant Name'.

    Categories (sign +1 = in the state value, not in the county sum of that state):
      offshore_no_county                 valid coordinates, no county (offshore)
      no_valid_coordinates               no valid coordinates (0 expected)
      state_field_county_elsewhere       'State' = s, but the point lies in a county of another state
    Category with sign -1 (in the county sum of s, not in the state value of s):
      county_here_state_field_elsewhere  point in a county of s, but 'State' is another state
    """
    op = op.copy()
    op["has_coords"] = op["has_coords"].astype(bool)
    op["county_state"] = op["county_fips"].str[:2]
    no_cnty = op["county_fips"].isna()
    cross = op["county_fips"].notna() & (op["county_state"] != op["state_fips"])
    spec = {
        "offshore_no_county": (no_cnty & op["has_coords"], "state_fips", +1),
        "no_valid_coordinates": (no_cnty & ~op["has_coords"], "state_fips", +1),
        "state_field_county_elsewhere": (cross, "state_fips", +1),
        "county_here_state_field_elsewhere": (cross, "county_state", -1),
    }
    cats: dict[str, list[Cat]] = {"net_summer_capacity_mw": [], "n_op_generators": [], "n_op_plants": []}
    lists: dict[str, pd.DataFrame] = {}
    for name, (mask, key, sign) in spec.items():
        sub = op[mask]
        gg = sub.groupby(key)
        n_rows = gg.size()
        n_ids = gg["Generator ID"].count()
        mw = gg["mw"].sum()
        pt = _plant_table(sub, key) if len(sub) else pd.DataFrame(columns=["plant_name", "key", "n_gens", "mw"])
        lists[name] = pt.assign(county_fips=sub.groupby("Plant Code")["county_fips"].first() if len(sub) else None)
        detail = {}
        if len(pt):
            for s, g in pt.groupby("key"):
                detail[s] = C.short_list([f"{r.plant_name} ({int(r.n_gens)} gen, {r.mw:.1f} MW)" for r in g.itertuples()])
        n_plants = pt.groupby("key").size() if len(pt) else pd.Series(dtype=int)
        cats["net_summer_capacity_mw"].append(Cat(name, n_rows, mw, sign, detail))
        cats["n_op_generators"].append(Cat(name, n_rows, n_ids, sign, detail))
        cats["n_op_plants"].append(Cat(name, n_plants, n_plants, sign, detail))
    return cats, lists


def main() -> None:
    import geopandas as gpd

    ap = C.base_parser("ADM1 builder: generation, EIA-860 (state = field 'State')")
    ap.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    args = ap.parse_args()
    snap, scope, exp = args.snapshot_date, C.make_scope(args.states), EXPECTED[args.states]
    d = Path(args.input_dir)
    n_cov = scope.n_states
    log.info("--states %s: %d states, %d counties", scope.mode, n_cov, scope.n_counties)

    plants_x = sorted(d.glob("2___Plant_Y*.xlsx"))
    gens_x = sorted(d.glob("3_1_Generator_Y*.xlsx"))
    if len(plants_x) != 1 or len(gens_x) != 1:
        raise SystemExit(f"STOP: expected one Plant and one Generator file in {d}, found {plants_x} / {gens_x}")

    input_paths = {"eia860_plant_xlsx": plants_x[0], "eia860_generator_xlsx": gens_x[0],
                   **C.shp_files(C.BOUNDARY_SHP, "county_shp")}
    inputs = C.hash_inputs(input_paths)

    log.info("Reading EIA-860 (about 15 s)...")
    plant_df = pd.read_excel(plants_x[0], sheet_name="Plant", header=1)
    gen_df = pd.read_excel(gens_x[0], sheet_name="Operable", header=1)

    # ---- COPY OF build_layer_generation_eia860.py (county rule); the state filter and the county
    #      loader are the only differences: both take the scope (contiguous = the original rule) ----
    op = gen_df[(gen_df["State"].isin(scope.usps)) & (gen_df["Status"] == "OP")].copy()
    plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude"]]
    merged = op.join(plant_lookup, on="Plant Code", rsuffix="_plant")
    lat = pd.to_numeric(merged["Latitude"], errors="coerce")
    lon = pd.to_numeric(merged["Longitude"], errors="coerce")
    valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
    points = gpd.GeoDataFrame(
        merged[valid].copy(), geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs="EPSG:4326")
    counties = C.load_counties(scope)
    points = points.to_crs(counties.crs)
    joined, n_unresolved = C.resolve_points_to_counties(points, counties, fallback_buffer_m=BOUNDARY_FALLBACK_M)
    joined_ok = joined[joined["fips"].notna()].copy()
    joined_ok["net_summer_capacity_mw"] = pd.to_numeric(joined_ok["Summer Capacity (MW)"], errors="coerce")
    agg = joined_ok.groupby("fips").agg(
        net_summer_capacity_mw=("net_summer_capacity_mw", "sum"),
        n_op_generators=("Generator ID", "count"),
        n_op_plants=("Plant Code", "nunique"),
    ).reset_index()
    rec = counties[["fips"]].merge(agg, on="fips", how="left")
    rec["net_summer_capacity_mw"] = rec["net_summer_capacity_mw"].fillna(0.0)
    rec["n_op_generators"] = rec["n_op_generators"].fillna(0).astype(int)
    rec["n_op_plants"] = rec["n_op_plants"].fillna(0).astype(int)
    # ---- end of COPY ----------------------------------------------------------------------
    rec = rec.set_index("fips")

    release = C.read_release("energy_generation_eia860_adm2.csv")
    identity = C.compare_county(
        LAYER, snap, rec, release,
        exact_cols=["n_op_generators", "n_op_plants"], float_cols=["net_summer_capacity_mw"])

    # ---- state rule (SPEC 2.2) -------------------------------------------------------------
    u2f = C.usps_to_fips(scope)
    op["mw"] = pd.to_numeric(op["Summer Capacity (MW)"], errors="coerce")
    op["state_fips"] = op["State"].map(u2f)
    if op["state_fips"].isna().any():
        raise SystemExit(f"STOP: a generator with a State outside the {n_cov} units")
    cf = joined["fips"]
    cf = cf[~cf.index.duplicated(keep="first")]
    op["county_fips"] = cf.reindex(op.index)
    op["has_coords"] = valid.reindex(op.index).fillna(False).astype(bool)

    g = op.groupby("state_fips")
    st = pd.DataFrame({
        "net_summer_capacity_mw": g["mw"].sum(),
        "n_op_generators": g["Generator ID"].count(),
        "n_op_plants": g["Plant Code"].nunique(),
    })
    covered = C.state_units(scope.fips).query("covered")["state_fips"]
    st = st.reindex(covered).fillna(0)
    st["net_summer_capacity_mw"] = st["net_summer_capacity_mw"].round(6)

    value_cols = ["net_summer_capacity_mw", "n_op_generators", "n_op_plants"]
    out = C.build_state_frame(st, value_cols, int_cols=["n_op_generators", "n_op_plants"], covered_fips=scope.fips)

    # ---- the 49 contiguous rows must equal the 0.2.0 build ---------------------------------
    identity_state = C.compare_state_prev(
        LAYER, snap, out, args.prev_date,
        exact_cols=["n_op_generators", "n_op_plants"], float_cols=["net_summer_capacity_mw"])

    # ---- reconciliation -----------------------------------------------------------------------
    cats, lists = eia_categories(op)
    rel_cols = {"net_summer_capacity_mw": "MW", "n_op_generators": "count", "n_op_plants": "count"}
    recon_parts = []
    for col, unit in rel_cols.items():
        ref = C.combined_reference(release, rec, [col])
        recon_parts.append(C.reconcile(
            LAYER_ID, col, unit, st[col], C.county_sums_by_state(ref, col, scope.fips), cats[col]))
    recon = pd.concat(recon_parts, ignore_index=True)
    max_resid = float(recon["residual"].abs().max())

    # ---- county table of the release (legacy format, new date) ---------------------------------
    tbl = counties[["fips", "NAME", "NAMELSAD"]].merge(
        rec.reset_index().rename(columns={"net_summer_capacity_mw": "net_summer_gen_mw"}), on="fips", how="left")
    tbl = tbl[["fips", "NAME", "NAMELSAD", "net_summer_gen_mw", "n_op_generators", "n_op_plants"]]

    # ---- numbers for the report ---------------------------------------------------------------
    off = lists["offshore_no_county"]
    cross = lists["state_field_county_elsewhere"]
    n_blank_id = int(op["Generator ID"].isna().sum())
    n_nonnum = int(op["mw"].isna().sum())
    county_gens = int(rec["n_op_generators"].sum())
    off_gens = int(off["n_gens"].sum()) if len(off) else 0
    nc = lists["no_valid_coordinates"]
    nocoord_gens = int(nc["n_gens"].sum()) if len(nc) else 0
    checks = [
        check("units: covered / not_covered", f"{n_cov} / {51 - n_cov}", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check(f"OP rows in the {n_cov} units", exp["op_rows"], len(op), note="pre-flight"),
        check(f"net_summer_capacity_mw, sum of {n_cov} states", exp["mw_states"],
              round(float(st["net_summer_capacity_mw"].sum()), 3), tol=0.15 if scope.mode == "all" else 0.05),
        check(f"n_op_plants, sum of {n_cov} states", exp["plants_states"], int(st["n_op_plants"].sum())),
        check("offshore stations (no county), MW", OFFSHORE_MW,
              round(float(off["mw"].sum()), 3) if len(off) else 0.0, tol=0.05),
        check("offshore stations (no county), count", OFFSHORE_PLANTS, int(len(off))),
        check("points that resolve to no county, count of generators", OFFSHORE_GENERATORS, int(n_unresolved)),
        check("n_op_generators by counties (recomputed)", exp["county_generators"], county_gens),
        check(f"n_op_generators, sum of {n_cov} states", exp["state_generators"], int(st["n_op_generators"].sum()),
              note=f"county sum {county_gens} + offshore generators {off_gens}"),
        check("n_op_generators: states = county sum + offshore + no-coordinate generators",
              county_gens + off_gens + nocoord_gens, int(st["n_op_generators"].sum()),
              note=f"offshore {off_gens}; without valid coordinates {nocoord_gens} (0 expected)"),
        check("plants/points landing in a county of ANOTHER state", CROSS_STATE_PLANTS, int(len(cross)),
              note="SPEC r6 2.8: accepted; state by the field 'State'; list below"),
        check("max |residual| of state_reconciliation", 0, max_resid, tol=1e-6),
    ]
    if scope.mode == "all":
        for f, (n_g, n_p, mw) in EXPECTED_AKHI.items():
            nm = {"02": "Alaska", "15": "Hawaii"}[f]
            checks += [
                check(f"{nm}: n_op_generators", n_g, int(st.loc[f, "n_op_generators"])),
                check(f"{nm}: n_op_plants", n_p, int(st.loc[f, "n_op_plants"])),
                check(f"{nm}: net_summer_capacity_mw", mw, round(float(st.loc[f, "net_summer_capacity_mw"]), 3), tol=0.06),
                check(f"{nm}: generators whose point lies in a county of another state or in no county", 0,
                      int(((op["state_fips"] == f) & (op["county_fips"].isna() |
                           (op["county_fips"].str[:2] != f))).sum())),
                check(f"{nm}: counties with a generator / counties", "-",
                      f"{int((rec.loc[rec.index.str[:2] == f, 'n_op_generators'] > 0).sum())} / "
                      f"{int((rec.index.str[:2] == f).sum())}"),
            ]
        checks += C.additivity_checks(out, args.prev_date, LAYER, value_cols, tol=1e-3)
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "states": scope.mode, "identity": identity,
        "identity_state_prev": identity_state, "checks": checks,
        "numbers": {
            "op_rows_in_scope": int(len(op)), "generators_without_id": n_blank_id,
            "capacity_not_numeric_in_scope": n_nonnum, "county_generators": county_gens,
            "county_unresolved_points": int(n_unresolved),
            "state_generators": int(st["n_op_generators"].sum()), "offshore_generators": off_gens,
            "no_valid_coordinates": int(len(lists["no_valid_coordinates"])),
            "county_rows_written": int(len(tbl)),
        },
        "lists": {
            "offshore_plants": off.reset_index().to_dict("records") if len(off) else [],
            "cross_state_plants": cross.reset_index().to_dict("records") if len(cross) else [],
        },
        "inputs": inputs,
    }

    cov_text = ("50 states + DC (the 51 units)" if scope.mode == "all"
                else "48 states + DC (the 49 units); Alaska and Hawaii not_covered")
    meta = {
        "source": "EIA Form 860, Schedule 3 (Generator, Operable/OP) + Schedule 2 (Plant)",
        "source_url": "https://www.eia.gov/electricity/data/eia860/",
        "vintage": "data year 2025, final release 2026-09-10",
        "license": "US government work, public domain (17 U.S.C. 105)",
        "coverage": cov_text,
        "edition": "2025 final", "current_through": "2025-12-31",
        "rule": "state = field 'State' of each Operable row with Status == 'OP'; "
                "net_summer_capacity_mw = sum of Summer Capacity (MW); n_op_generators counts rows with a "
                "Generator ID; n_op_plants counts distinct Plant Code",
        "states_mode": scope.mode,
        "n_units_covered": n_cov, "n_units_not_covered": 51 - n_cov,
        "known_gaps": (
            f"Offshore stations are inside their states but in no county: {int(len(off))} stations, "
            f"{float(off['mw'].sum()) if len(off) else 0.0:.1f} MW. "
            f"{n_blank_id} generator row(s) without a Generator ID are not counted in n_op_generators "
            f"(as in the county layer). {n_nonnum} OP rows in the {n_cov} units have no numeric Summer Capacity "
            "and add nothing to the sum. "
            + ("Alaska and Hawaii: every generator point lies inside a county of its own state; the county name "
               "in the source can differ from the county of the boundary file (Alaska boroughs and census "
               "areas were reorganised), the county is taken by the coordinate. " if scope.mode == "all" else "")
            + "Factual draft; wording by [RES]7."
        ),
        "inputs": inputs, "boundary_file": str(C.BOUNDARY_SHP),
        "identity_with_release_0_1_0": identity, "identity_state_with_0_2_0": identity_state,
    }
    csv_path = C.write_layer_csv(LAYER, out, meta, snap)

    county_meta = C.read_legacy_meta(LEGACY_META)
    county_meta.update({
        "coverage": cov_text, "states_mode": scope.mode,
        "n_units_covered": int(len(joined_ok)), "n_units_no_data": int(n_unresolved),
        "rebuilt_for": "abf-layers 0.3.0 (SPEC_USA_AKHI_v0_3_0 r2); county rule unchanged, see build_adm1_generation_eia860.py",
        "boundary_file": str(C.BOUNDARY_SHP),
        "boundary_file_sha256": inputs["county_shp.shp"]["sha256"],
        "input": str(d), "identity_with_release_0_1_0": identity,
    })
    county_csv = C.write_county_table("generation_eia860", tbl, county_meta, snap)
    report["county_table"] = {"file": county_csv.name, "rows": int(len(tbl)),
                              "text_vs_legacy": C.compare_text_to_legacy(county_csv, C.OUTPUT_DIR / LEGACY_TABLE)}
    C.assert_inputs_unchanged(inputs, input_paths)
    C.write_part(LAYER, snap, report, recon)
    log.info("DONE. %s ; %s", csv_path, county_csv)
    C.stop_if_failed(checks, LAYER)


if __name__ == "__main__":
    main()
