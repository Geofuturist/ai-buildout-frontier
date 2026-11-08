r"""
build_adm1_generation_eia860.py
===============================
SPEC_USA_states_v0_2_0 r5, section 2.2: generation by state (EIA-860, Operable, Status == 'OP').

State = field 'State' of the generator row (no coordinates needed), so offshore plants
fall into their states. In the same run the county layer is recomputed with the SAME rule
as build_layer_generation_eia860.py (copied below, marked "COPY OF") and compared with the
CSV of release 0.1.0 (SPEC 2.1 item 5). Any difference stops the build.

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_generation_eia860.py --snapshot-date 20261101

Writes to data\conus\:
    layer_generation_eia860_adm1_<date>.csv, layer_generation_eia860_adm1_meta.json,
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

EXPECTED = {
    "mw_states": 1254379.4,     # 1,254,208.1 counties + 171.3 offshore
    "plants_states": 13593,     # 13,590 + 3
    "offshore_mw": 171.3,
    "offshore_plants": 3,
    "county_generators": 24957,
    "op_rows_49": 24961,
}


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
    snap = args.snapshot_date
    d = Path(args.input_dir)

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

    # ---- COPY OF build_layer_generation_eia860.py (county rule) -------------------------
    op = gen_df[(gen_df["State"].isin(C.CONUS_STATES_USPS)) & (gen_df["Status"] == "OP")].copy()
    plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude"]]
    merged = op.join(plant_lookup, on="Plant Code", rsuffix="_plant")
    lat = pd.to_numeric(merged["Latitude"], errors="coerce")
    lon = pd.to_numeric(merged["Longitude"], errors="coerce")
    valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
    points = gpd.GeoDataFrame(
        merged[valid].copy(), geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs="EPSG:4326")
    counties = C.load_conus_counties()
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
    u2f = C.usps_to_fips()
    op["mw"] = pd.to_numeric(op["Summer Capacity (MW)"], errors="coerce")
    op["state_fips"] = op["State"].map(u2f)
    if op["state_fips"].isna().any():
        raise SystemExit("STOP: a generator with a State outside the 49 units")
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
    covered = C.state_units().query("covered")["state_fips"]
    st = st.reindex(covered).fillna(0)
    st["net_summer_capacity_mw"] = st["net_summer_capacity_mw"].round(6)

    value_cols = ["net_summer_capacity_mw", "n_op_generators", "n_op_plants"]
    out = C.build_state_frame(st, value_cols, int_cols=["n_op_generators", "n_op_plants"])

    # ---- reconciliation -----------------------------------------------------------------------
    cats, lists = eia_categories(op)
    rel_cols = {"net_summer_capacity_mw": "MW", "n_op_generators": "count", "n_op_plants": "count"}
    recon_parts = []
    for col, unit in rel_cols.items():
        recon_parts.append(C.reconcile(
            LAYER_ID, col, unit, st[col], C.county_sums_by_state(release, col), cats[col]))
    recon = pd.concat(recon_parts, ignore_index=True)
    max_resid = float(recon["residual"].abs().max())

    # ---- numbers for the report ---------------------------------------------------------------
    off = lists["offshore_no_county"]
    cross = lists["state_field_county_elsewhere"]
    n_blank_id = int(op["Generator ID"].isna().sum())
    n_nonnum = int(op["mw"].isna().sum())
    county_gens = int(rec["n_op_generators"].sum())
    off_gens = int(off["n_gens"].sum()) if len(off) else 0
    checks = [
        check("units: covered / not_covered", "49 / 2", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check("OP rows in the 49 units", EXPECTED["op_rows_49"], len(op), note="pre-flight: 24,961"),
        check("net_summer_capacity_mw, sum of 49 states", EXPECTED["mw_states"],
              round(float(st["net_summer_capacity_mw"].sum()), 3), tol=0.05),
        check("n_op_plants, sum of 49 states", EXPECTED["plants_states"], int(st["n_op_plants"].sum())),
        check("offshore stations (no county), MW", EXPECTED["offshore_mw"],
              round(float(off["mw"].sum()), 3) if len(off) else 0.0, tol=0.05),
        check("offshore stations (no county), count", EXPECTED["offshore_plants"], int(len(off))),
        check("n_op_generators by counties (recomputed)", EXPECTED["county_generators"], county_gens),
        check("n_op_generators, sum of 49 states", county_gens + off_gens, int(st["n_op_generators"].sum()),
              note=f"county sum {county_gens} + offshore generators {off_gens}"),
        check("plants/points landing in a county of ANOTHER state", 0, int(len(cross)),
              note="SPEC 2.2 expects 0 (marked with a warning sign); list below if > 0"),
        check("max |residual| of state_reconciliation", 0, max_resid, tol=1e-6),
    ]
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "identity": identity,
        "checks": checks,
        "numbers": {
            "op_rows_49": int(len(op)), "generators_without_id": n_blank_id,
            "capacity_not_numeric_in_49": n_nonnum, "county_generators": county_gens,
            "county_unresolved_points": int(n_unresolved),
            "state_generators": int(st["n_op_generators"].sum()), "offshore_generators": off_gens,
            "no_valid_coordinates": int(len(lists["no_valid_coordinates"])),
        },
        "lists": {
            "offshore_plants": off.reset_index().to_dict("records") if len(off) else [],
            "cross_state_plants": cross.reset_index().to_dict("records") if len(cross) else [],
        },
        "inputs": inputs,
    }

    meta = {
        "source": "EIA Form 860, Schedule 3 (Generator, Operable/OP) + Schedule 2 (Plant)",
        "source_url": "https://www.eia.gov/electricity/data/eia860/",
        "vintage": "data year 2025, final release 2026-09-10",
        "license": "US government work, public domain (17 U.S.C. 105)",
        "coverage": "48 states + DC (the 49 units); Alaska and Hawaii not_covered",
        "edition": "2025 final", "current_through": "2025-12-31",
        "rule": "state = field 'State' of each Operable row with Status == 'OP'; "
                "net_summer_capacity_mw = sum of Summer Capacity (MW); n_op_generators counts rows with a "
                "Generator ID; n_op_plants counts distinct Plant Code",
        "n_units_covered": 49, "n_units_not_covered": 2,
        "known_gaps": (
            f"Offshore stations are inside their states but in no county: {int(len(off))} stations, "
            f"{float(off['mw'].sum()) if len(off) else 0.0:.1f} MW. "
            f"{n_blank_id} generator row(s) without a Generator ID are not counted in n_op_generators "
            f"(as in the county layer). {n_nonnum} OP rows in the 49 units have no numeric Summer Capacity "
            "and add nothing to the sum. Factual draft; wording by [RES]7."
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
