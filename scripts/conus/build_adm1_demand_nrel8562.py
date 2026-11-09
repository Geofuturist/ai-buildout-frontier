r"""
build_adm1_demand_nrel8562.py
=============================
SPEC_USA_states_v0_2_0 r5, section 2.4 (0.2.0) and SPEC_USA_AKHI_v0_3_0 r2 (0.3.0): peak demand by state
(NREL OEDI 8562, year 2023).

The source covers only the contiguous United States (pre-flight 08.11.2026: no profile column for any
county of Alaska or Hawaii), so they stay not_covered with empty values. --states is accepted for
uniformity and does not change the result; the run STOPS if the file has a column of either state.

State hourly series = sum of the profile columns of the state's covered counties in every hour;
peak_demand_mw = the maximum of that series (not the sum of county peaks). The county peaks are
recomputed with the rule of build_layer_demand_nrel.py (COPY OF, marked) and compared with the CSV
of release 0.1.0. Any difference, a missing value in any column in any hour, or a violated
inequality  max county peak <= state peak <= sum of county peaks  stops the build. The 49 state rows are
also compared with the 0.2.0 build.

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_demand_nrel8562.py --snapshot-date 20261109

Writes to data\conus\: layer_demand_nrel8562_adm1_<date>.csv + _meta.json, layer_demand_nrel8562_<date>.csv +
_meta.json (county table of the release, legacy format), adm1_part_* / adm1_recon_part_*.

The file is read whole (1.7 GB, a few seconds, about 3 GB of memory).
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import
from adm1_common import check, log
from pathlib import Path

import numpy as np
import pandas as pd

LAYER = "demand_nrel8562"
LAYER_ID = "energy_demand_nrel8562_adm1"
DEFAULT_H5 = r"D:\GISData\Energy\USA\historic_load_hourly_2016_2023_county.h5"
NREL_YEAR = 2023  # COPY OF build_layer_demand_nrel.py
SUM_COUNTY_PEAKS_EXPECTED = 822740.1
LEGACY_META = "layer_demand_nrel8562_meta.json"
LEGACY_TABLE = "layer_demand_nrel8562_20260912.csv"


def state_peaks(year_df: pd.DataFrame, fips_cols: dict[str, str]) -> pd.DataFrame:
    """Per state: peak of the hourly sum, hour of the peak (UTC), sum of county peaks, largest county peak.

    year_df: hourly profiles, columns named by county FIPS (without the 'p'); fips_cols maps
    column name -> state FIPS (only the covered counties).
    Raises ValueError if max county peak <= state peak <= sum of county peaks is violated.
    """
    rows = []
    for s in sorted(set(fips_cols.values())):
        cols = [c for c, st in fips_cols.items() if st == s]
        block = year_df[cols]
        series = block.sum(axis=1)
        peak = float(series.max())
        county_peaks = block.max(axis=0)
        sum_peaks, max_county = float(county_peaks.sum()), float(county_peaks.max())
        if not (max_county <= peak + 1e-6 and peak <= sum_peaks + 1e-6):
            raise ValueError(f"state {s}: max county {max_county} <= state peak {peak} <= sum {sum_peaks} violated")
        hour = series.idxmax()
        rows.append({"state_fips": s, "peak_demand_mw": peak, "peak_hour_utc": pd.Timestamp(hour).strftime("%Y-%m-%d %H:%M UTC"),
                     "sum_county_peaks_mw": sum_peaks, "max_county_peak_mw": max_county,
                     "ratio_state_to_sum": peak / sum_peaks if sum_peaks else np.nan, "n_county_columns": len(cols)})
    return pd.DataFrame(rows).set_index("state_fips")


def main() -> None:
    ap = C.base_parser("ADM1 builder: peak demand, NREL OEDI 8562 (state = max of hourly sum of counties)")
    ap.add_argument("--h5", default=DEFAULT_H5)
    args = ap.parse_args()
    snap, scope = args.snapshot_date, C.make_scope(args.states)
    h5 = Path(args.h5)
    log.info("--states %s accepted; the source covers only the contiguous states, the result is the same", scope.mode)

    input_paths = {"nrel_oedi8562_h5": h5}
    inputs = C.hash_inputs(input_paths)

    log.info("Reading the HDF5 file whole (Fixed format)...")
    store = pd.HDFStore(str(h5), mode="r")
    try:
        df_full = store["/data"]
    finally:
        store.close()
    year = df_full.loc[f"{NREL_YEAR}-01-01":f"{NREL_YEAR}-12-31"].copy()
    del df_full
    log.info("%d: %d rows x %d columns; index time zone: %s", NREL_YEAR, len(year), year.shape[1], year.index.tz)
    n_nan = int(year.isna().sum().sum())
    if n_nan:
        raise SystemExit(f"STOP: {n_nan} missing values in the {NREL_YEAR} profiles (SPEC 2.4)")

    # ---- COPY OF build_layer_demand_nrel.py (county peaks) ---------------------------------
    peak = year.max(axis=0)
    peak.index = [c[1:] if c.startswith("p") else c for c in peak.index]  # 'p51001' -> '51001'
    # ---- end of COPY ------------------------------------------------------------------------
    year.columns = [c[1:] if c.startswith("p") else c for c in year.columns]
    n_akhi_cols = int(sum(c[:2] in C.AKHI_FIPS for c in year.columns))  # SPEC_USA_AKHI 1: premise "no columns"
    if n_akhi_cols:
        raise SystemExit(f"STOP: {n_akhi_cols} profile columns of Alaska/Hawaii; the pre-flight found none. "
                         "The coverage rule is a decision for [ARCH7].")

    counties = C.load_conus_counties()
    rec = counties[["fips"]].merge(peak.rename("peak_demand_mw").rename_axis("fips").reset_index(), on="fips", how="left")
    rec = rec.set_index("fips")
    rec["coverage_status"] = np.where(rec["peak_demand_mw"].notna(), "covered", "not_covered")

    release = C.read_release("energy_demand_nrel8562_adm2.csv")
    identity = C.compare_county(LAYER, snap, rec, release, float_cols=["peak_demand_mw"])

    # ---- columns of the state sums = exactly the covered counties of the layer (SPEC 2.4) -------
    covered = set(release.loc[(release["coverage_status"] == "covered") & release["fips"].notna(), "fips"])
    file_cols = set(year.columns)
    not_in_layer = sorted(file_cols - covered)
    not_in_file = sorted(covered - file_cols)
    if not_in_file:
        raise SystemExit(f"STOP: covered counties without a profile column: {not_in_file[:10]}")
    fips_cols = {c: c[:2] for c in year.columns if c in covered}
    n_by_state = pd.Series(fips_cols).value_counts()
    cov_by_state = pd.Series({f: f[:2] for f in covered}).value_counts()
    if not (n_by_state.sort_index() == cov_by_state.sort_index()).all():
        raise SystemExit("STOP: number of columns per state != number of covered counties per state")

    sp = state_peaks(year, fips_cols)  # raises on a violated inequality
    st = sp[["peak_demand_mw"]].copy()
    st["peak_demand_mw"] = st["peak_demand_mw"].round(6)
    out = C.build_state_frame(st, ["peak_demand_mw"])
    identity_state = C.compare_state_prev(LAYER, snap, out, args.prev_date, float_cols=["peak_demand_mw"])

    sums = C.county_sums_by_state(release, "peak_demand_mw")
    recon = pd.DataFrame({
        "layer_id": LAYER_ID, "unit_id": [f"USA-1-{s}" for s in sp.index], "field": "peak_demand_mw", "unit": "MW",
        "state_value": sp["peak_demand_mw"].round(6).values,
        "county_sum": sums.reindex(sp.index).round(6).values,
        "difference": (sp["peak_demand_mw"] - sums.reindex(sp.index)).round(6).values,
        "residual": np.nan,  # no categories: the state peak is not a sum (SPEC 2.4 / 2.6)
        "nrel_peak_hour_utc": sp["peak_hour_utc"].values,
        "nrel_max_county_peak_mw": sp["max_county_peak_mw"].round(6).values,
        "nrel_ratio_state_to_sum": sp["ratio_state_to_sum"].round(6).values,
        "nrel_n_county_columns": sp["n_county_columns"].values,
        "detail": "state value = peak of the hourly sum of its counties; county_sum = sum of county peaks",
    })

    sum_state_peaks = float(sp["peak_demand_mw"].sum())
    sum_county_peaks = float(release.loc[release["coverage_status"] == "covered", "peak_demand_mw"].sum())
    checks = [
        check("profile columns of Alaska or Hawaii in the file", 0, n_akhi_cols),
        check("units: covered / not_covered", "49 / 2", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check("rows in the 2023 profiles", 8760, int(len(year))),
        check("missing values in 2023 profiles", 0, n_nan),
        check("sum of county peaks (release 0.1.0 CSV)", SUM_COUNTY_PEAKS_EXPECTED, round(sum_county_peaks, 3), tol=0.05),
        check("sum of the 49 state peaks < sum of county peaks", f"< {SUM_COUNTY_PEAKS_EXPECTED}",
              round(sum_state_peaks, 3), note="strictly smaller if counties peak in different hours"),
        check("Connecticut: county columns", 9, int(sp.loc["09", "n_county_columns"])),
        check("states with a peak", 49, int(len(sp))),
        check("inequality max county <= state <= sum of county peaks violated in", 0, 0,
              note="a violation stops the build"),
    ]
    for c in checks:
        if c["name"].startswith("sum of the 49 state peaks"):
            c["ok"] = sum_state_peaks < SUM_COUNTY_PEAKS_EXPECTED
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "states": scope.mode, "identity": identity,
        "identity_state_prev": identity_state, "checks": checks,
        "numbers": {
            "sum_state_peaks_mw": round(sum_state_peaks, 3), "sum_county_peaks_mw": round(sum_county_peaks, 3),
            "year": NREL_YEAR, "index_time_zone": str(year.index.tz),
            "peak_hours_are": "UTC (the index of the file is UTC)",
        },
        "lists": {
            "file_columns_not_in_layer": not_in_layer,
            "per_state": sp.reset_index().round(6).to_dict("records"),
        },
        "inputs": inputs,
    }
    meta = {
        "source": "NREL/NLR OEDI submission 8562 - Hourly Electricity Demand Profiles for US Counties",
        "source_url": "https://data.openei.org/submissions/8562",
        "vintage": f"hourly data 2016-2023, year {NREL_YEAR} taken",
        "license": "see the OEDI submission 8562 page (open access, no registration)",
        "coverage": "48 states + DC (the 49 units); Alaska and Hawaii are absent from the source",
        "rule": "state peak = maximum over the 8,760 hours of the sum of the profiles of the state's covered "
                "counties; not the sum of county peaks. Hours are UTC.",
        "n_units_covered": 49, "n_units_not_covered": 2,
        "known_gaps": (
            f"The sum of the 49 state peaks ({sum_state_peaks:,.1f} MW) is smaller than the sum of county peaks "
            f"({sum_county_peaks:,.1f} MW) because counties peak in different hours. "
            f"{len(not_in_layer)} columns of the file are not in the layer. Factual draft; wording by [RES]7."
        ),
        "inputs": inputs, "boundary_file": str(C.BOUNDARY_SHP),
        "identity_with_release_0_1_0": identity,
    }
    meta["alaska_hawaii"] = "not_covered: the source has no profile column of any Alaska or Hawaii county; empty values, not zero"
    csv_path = C.write_layer_csv(LAYER, out, meta, snap)

    tbl = counties[["fips", "NAME", "NAMELSAD"]].merge(rec.reset_index()[["fips", "peak_demand_mw"]], on="fips", how="left")
    county_meta = C.read_legacy_meta(LEGACY_META)
    county_meta.update({
        "states_mode": scope.mode,
        "rebuilt_for": "abf-layers 0.3.0 (SPEC_USA_AKHI_v0_3_0 r2); county rule unchanged; Alaska and Hawaii "
                       "counties are not in this table: the source does not cover them (not_covered by the frame)",
        "boundary_file": str(C.BOUNDARY_SHP), "input": str(h5), "identity_with_release_0_1_0": identity,
    })
    county_csv = C.write_county_table("demand_nrel8562", tbl, county_meta, snap)
    report["county_table"] = {"file": county_csv.name, "rows": int(len(tbl)),
                              "text_vs_legacy": C.compare_text_to_legacy(county_csv, C.OUTPUT_DIR / LEGACY_TABLE)}
    C.assert_inputs_unchanged(inputs, input_paths)
    C.write_part(LAYER, snap, report, recon)
    log.info("DONE. %s ; %s", csv_path, county_csv)
    C.stop_if_failed(checks, LAYER)


if __name__ == "__main__":
    main()
