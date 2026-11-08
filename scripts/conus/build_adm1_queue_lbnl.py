r"""
build_adm1_queue_lbnl.py
========================
SPEC_USA_states_v0_2_0 r5, section 2.3 (0.2.0) and SPEC_USA_AKHI_v0_3_0 r2 (0.3.0): interconnection
queue by state (LBNL Queued Up 2026).

The source does not cover Alaska and Hawaii (pre-flight 08.11.2026: no record with state AK/HI and no
county code 02xxx/15xxx in any status), so they stay not_covered with empty values, never 0 (P2). The
--states switch is accepted for uniformity with the other builders and does not change the result;
instead the run STOPS if the file contains a record of either state (the premise would be false).

State = field 'state' of the record (only the 49 codes count). The county layer is recomputed
with the rule of build_layer_queue_lbnl.py run with  --crosswalk --ct-not-covered
--drop-nonpositive  (the keys are restored from legacy_meta, SPEC r5 2.7) and compared with the
CSV of release 0.1.0. Any difference stops the build. The 49 state rows are also compared with the 0.2.0 build.

Run (from the repository root, cmd):
    python scripts\conus\build_adm1_queue_lbnl.py --snapshot-date 20261109

Writes to data\conus\: layer_queue_lbnl_adm1_<date>.csv + _meta.json, layer_queue_lbnl_<date>.csv + _meta.json
(county table of the release, legacy format), adm1_part_* / adm1_recon_part_*.
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import
from adm1_common import Cat, check, log
from pathlib import Path

import numpy as np
import pandas as pd

LAYER = "queue_lbnl"
LAYER_ID = "energy_queue_lbnl_adm1"
DEFAULT_XLSX = r"D:\GISData\Energy\USA\lbnl_ix_queue_data_file_thru2025.xlsx"
SHEET = "03. Complete Queue Data"
LEGACY_META = "layer_queue_lbnl_20261009_r2_meta.json"
LEGACY_TABLE = "layer_queue_lbnl_20261009_r2.csv"
CT_NULL_MEANING = ("The source codes Connecticut projects by pre-2022 counties, "
                   "which do not map onto the 2022 planning regions")  # COPY OF build_layer_queue_lbnl.py

EXPECTED = {"active": 8513, "state_n": 8449, "state_mw": 1740502.1, "no_county_n": 35, "no_county_mw": 11280.7,
            "ct_n": 7, "ct_mw": 678.2, "outside_n": 53, "outside_mw": 8813.0, "nonpos_n": 11, "nonpos_mw": -193.5,
            "mismatch_n": 5}
MISMATCH_IDS_SPEC = {"Q362", "BHBE G20", "956747", "J3785", "GEN-2020-065"}


def poi_request_mw(mw1, mw2, mw3):
    """COPY OF build_layer_queue_lbnl.py: max(mw1, mw2, mw3), skipping missing values."""
    vals = [v for v in (C.safe_float(mw1), C.safe_float(mw2), C.safe_float(mw3)) if v is not None]
    return max(vals) if vals else None


def lbnl_classify(active: pd.DataFrame, valid_fips: set[str], u2f: dict[str, str]) -> pd.DataFrame:
    """Annotate active records with the state rule (SPEC 2.3).

    Needs columns: state (postal code or NaN), fips_str (5 digits or NaN), poi_mw.
    Adds:
      state_fips   FIPS of the 'state' field if it is one of the 49 codes, else NaN
      cls          outside_49 | nonpositive | no_capacity | state_rule
      in_layer     True if the record is in the county sums (valid county, not Connecticut, capacity > 0)
      county_state state FIPS of the county code (only if in_layer)
      sub          for state_rule records, why the state value differs from the county sums:
                   both | cross_state_county | connecticut | no_county_code | county_code_not_in_layer
    """
    df = active.copy()
    df["state_fips"] = df["state"].map(lambda v: u2f.get(v.strip()) if isinstance(v, str) else None)
    poi = pd.to_numeric(df["poi_mw"], errors="coerce")
    df["poi_mw"] = poi
    outside = df["state_fips"].isna()
    nonpos = ~outside & poi.notna() & (poi <= 0)
    nocap = ~outside & poi.isna()
    df["cls"] = np.where(outside, "outside_49", np.where(nonpos, "nonpositive",
                         np.where(nocap, "no_capacity", "state_rule")))
    in_valid = df["fips_str"].isin(valid_fips)
    df["in_layer"] = in_valid & ~df["fips_str"].fillna("").str.startswith("09") & poi.notna() & (poi > 0)
    df["county_state"] = df["fips_str"].where(df["in_layer"]).str[:2]
    sub = pd.Series("", index=df.index, dtype=object)
    sr = df["cls"] == "state_rule"
    both = sr & df["in_layer"] & (df["county_state"] == df["state_fips"])
    cross = sr & df["in_layer"] & (df["county_state"] != df["state_fips"])
    ct = sr & ~df["in_layer"] & (df["state_fips"] == "09")
    nocnty = sr & ~df["in_layer"] & ~ct & df["fips_str"].isna()
    other = sr & ~df["in_layer"] & ~ct & ~nocnty
    sub[both] = "both"
    sub[cross] = "cross_state_county"
    sub[ct] = "connecticut"
    sub[nocnty] = "no_county_code"
    sub[other] = "county_code_not_in_layer"
    df["sub"] = sub
    return df


def lbnl_cats(df: pd.DataFrame) -> dict[str, list[Cat]]:
    """Reconciliation categories per field (queue_mw_active, n_active_projects)."""
    def label(r) -> str:
        st = r.state if isinstance(r.state, str) else "no state"
        return f"{r.q_id} ({st}, county code {r.fips_str}, {r.poi_mw:.1f} MW)"

    spec = {
        "connecticut": (df["sub"] == "connecticut", "state_fips", +1),
        "no_county_code": (df["sub"] == "no_county_code", "state_fips", +1),
        "county_code_not_in_layer": (df["sub"] == "county_code_not_in_layer", "state_fips", +1),
        "state_field_county_elsewhere": (df["sub"] == "cross_state_county", "state_fips", +1),
        "county_here_state_field_elsewhere": (
            df["in_layer"] & (df["cls"].isin(["state_rule", "outside_49"])) &
            (df["state_fips"].isna() | (df["state_fips"] != df["county_state"])), "county_state", -1),
    }
    cats: dict[str, list[Cat]] = {"queue_mw_active": [], "n_active_projects": []}
    for name, (mask, key, sign) in spec.items():
        sub = df[mask]
        gg = sub.groupby(key)
        n = gg.size()
        mw = gg["poi_mw"].sum()
        detail = {}
        if name in ("state_field_county_elsewhere", "county_here_state_field_elsewhere") and len(sub):
            for s, g in sub.groupby(key):
                detail[s] = C.short_list([label(r) for r in g.itertuples()])
        cats["queue_mw_active"].append(Cat(name, n, mw, sign, detail))
        cats["n_active_projects"].append(Cat(name, n, n, sign, detail))
    return cats


def main() -> None:
    ap = C.base_parser("ADM1 builder: interconnection queue, LBNL Queued Up (state = field 'state')")
    ap.add_argument("--input-file", default=DEFAULT_XLSX)
    ap.add_argument("--crosswalk", default=str(C.REPO / "boundaries" / "code_crosswalk_exact.csv"))
    args = ap.parse_args()
    snap, scope = args.snapshot_date, C.make_scope(args.states)
    xlsx, crosswalk = Path(args.input_file), Path(args.crosswalk)
    log.info("--states %s accepted; the source covers only the contiguous states, the result is the same", scope.mode)

    input_paths = {"lbnl_queue_xlsx": xlsx, "code_crosswalk_exact_csv": crosswalk,
                   **C.shp_files(C.BOUNDARY_SHP, "county_shp")}
    inputs = C.hash_inputs(input_paths)

    log.info("Reading LBNL Queued Up (about 10 s)...")
    df = pd.read_excel(xlsx, sheet_name=SHEET, header=1)
    # ---- coverage premise (SPEC_USA_AKHI 1): no record of Alaska or Hawaii in any status ----------
    state_col = df["state"].map(lambda v: v.strip() if isinstance(v, str) else None)
    code_col = df["fips_codes" if "fips_codes" in df.columns else "fips_code"].map(
        lambda v: str(int(v)).zfill(5) if pd.notna(v) and str(v).strip().upper() != "NA" else "")
    n_akhi_state = int(state_col.isin(C.AKHI_USPS).sum())
    n_akhi_code = int(code_col.str[:2].isin(C.AKHI_FIPS).sum())
    if n_akhi_state or n_akhi_code:
        raise SystemExit(f"STOP: the file has records of Alaska/Hawaii (state field {n_akhi_state}, county code "
                         f"{n_akhi_code}); the pre-flight found none. The coverage rule is a decision for [ARCH7].")
    log.info("Alaska/Hawaii records in all %d rows: 0 (state field), 0 (county code)", len(df))
    # ---- COPY OF build_layer_queue_lbnl.py (county rule, keys --crosswalk --ct-not-covered
    #      --drop-nonpositive) -----------------------------------------------------------------
    renames = {"fips_code": "fips_codes", "mw_1": "mw1", "mw_2": "mw2", "mw_3": "mw3"}
    renames = {k: v for k, v in renames.items() if k in df.columns and v not in df.columns}
    if renames:
        df = df.rename(columns=renames)
    active = df[df["q_status"] == "active"].copy()
    active["fips_str"] = active["fips_codes"].apply(
        lambda v: str(int(v)).zfill(5) if pd.notna(v) and str(v).strip().upper() != "NA" else None)
    active["poi_mw"] = active.apply(lambda r: poi_request_mw(r["mw1"], r["mw2"], r["mw3"]), axis=1)
    counties = C.load_conus_counties()
    valid_fips = set(counties["fips"])
    cw = pd.read_csv(crosswalk, dtype=str)
    recoded = []
    for _, c in cw.iterrows():
        m = active["fips_str"] == c["old_fips"].zfill(5)
        recoded.append({"old_fips": c["old_fips"], "new_fips": c["new_fips"],
                        "records": int(m.sum()), "mw": float(active.loc[m, "poi_mw"].sum())})
        active.loc[m, "fips_str"] = c["new_fips"].zfill(5)
    ct_old = active[active["fips_str"].fillna("").str.startswith("09") & ~active["fips_str"].isin(valid_fips)]
    ct_new = active[active["fips_str"].fillna("").str.startswith("09") & active["fips_str"].isin(valid_fips)]
    active_conus = active[active["fips_str"].isin(valid_fips)].copy()
    bad = active_conus["poi_mw"].notna() & (active_conus["poi_mw"] <= 0)
    active_conus = active_conus[~bad].copy()
    agg = active_conus.groupby("fips_str").agg(
        queue_mw_active=("poi_mw", "sum"), n_active_projects=("poi_mw", "count"),
    ).reset_index().rename(columns={"fips_str": "fips"})
    rec = counties.merge(agg, on="fips", how="left")
    rec["queue_mw_active"] = rec["queue_mw_active"].fillna(0.0)
    rec["n_active_projects"] = rec["n_active_projects"].fillna(0).astype(int)
    ctm = rec["fips"].str.startswith("09")
    rec["queue_mw_active"] = rec["queue_mw_active"].where(~ctm)
    rec["n_active_projects"] = rec["n_active_projects"].astype("Int64").where(~ctm)
    rec["coverage_status"] = ctm.map({True: "not_covered", False: "covered"})
    rec["coverage_note"] = ctm.map({True: CT_NULL_MEANING, False: ""})
    # ---- end of COPY ---------------------------------------------------------------------------
    rec = rec.set_index("fips")

    release = C.read_release("energy_queue_lbnl_adm2.csv")
    identity = C.compare_county(
        LAYER, snap, rec, release, exact_cols=["n_active_projects"], float_cols=["queue_mw_active"])

    # ---- state rule (SPEC 2.3) -----------------------------------------------------------------
    u2f = C.usps_to_fips()
    cl = lbnl_classify(active, valid_fips, u2f)
    sr = cl[cl["cls"] == "state_rule"]
    gg = sr.groupby("state_fips")
    st = pd.DataFrame({"queue_mw_active": gg["poi_mw"].sum(), "n_active_projects": gg.size()})
    covered = C.state_units().query("covered")["state_fips"]  # 49: the source does not cover Alaska and Hawaii
    st = st.reindex(covered).fillna(0)
    st["queue_mw_active"] = st["queue_mw_active"].round(6)
    out = C.build_state_frame(st, ["queue_mw_active", "n_active_projects"], int_cols=["n_active_projects"])
    identity_state = C.compare_state_prev(LAYER, snap, out, args.prev_date,
                                          exact_cols=["n_active_projects"], float_cols=["queue_mw_active"])

    # internal consistency: my classification must give exactly the county sums of the copied rule
    internal = cl[cl["in_layer"]].groupby("county_state")["poi_mw"].sum()
    rule_sum = rec["queue_mw_active"].groupby(rec.index.str[:2]).sum()
    if (internal.reindex(rule_sum.index).fillna(0) - rule_sum.fillna(0)).abs().max() > 1e-6:
        raise SystemExit("STOP: classification and county rule disagree (internal check)")

    cats = lbnl_cats(cl)
    recon = pd.concat([
        C.reconcile(LAYER_ID, "queue_mw_active", "MW", st["queue_mw_active"],
                    C.county_sums_by_state(release, "queue_mw_active"), cats["queue_mw_active"]),
        C.reconcile(LAYER_ID, "n_active_projects", "count", st["n_active_projects"],
                    C.county_sums_by_state(release, "n_active_projects"), cats["n_active_projects"]),
    ], ignore_index=True)
    max_resid = float(recon["residual"].abs().max())

    # ---- numbers for the report ------------------------------------------------------------------
    ct_all = sr[sr["state_fips"] == "09"]
    no_fips_all = sr[sr["fips_str"].isna()]
    outside = cl[cl["cls"] == "outside_49"]
    nonpos = cl[cl["cls"] == "nonpositive"]
    cross = sr[sr["sub"] == "cross_state_county"]
    c_side = cl[cl["in_layer"] & (cl["state_fips"].isna() | (cl["state_fips"] != cl["county_state"]))]

    def rows(d: pd.DataFrame) -> list[dict]:
        return [{"q_id": str(r.q_id), "region": str(getattr(r, "region", "")), "state": r.state,
                 "county_fips": r.fips_str, "mw": float(r.poi_mw)} for r in d.itertuples()]

    cross_ids = {str(x) for x in cross["q_id"]}
    checks = [
        check("records with state AK or HI (all statuses)", 0, n_akhi_state),
        check("records with a county code 02xxx or 15xxx (all statuses)", 0, n_akhi_code),
        check("units: covered / not_covered", "49 / 2", f"{int(out.coverage_status.eq('covered').sum())} / "
              f"{int(out.coverage_status.eq('not_covered').sum())}"),
        check("active records", EXPECTED["active"], int(len(cl))),
        check("state rule: projects (49 states)", EXPECTED["state_n"], int(len(sr))),
        check("state rule: queue_mw_active, MW", EXPECTED["state_mw"], round(float(sr["poi_mw"].sum()), 3), tol=0.05),
        check("active = state rule + outside + nonpositive (+ no capacity)", EXPECTED["active"],
              int(len(sr) + len(outside) + len(nonpos) + (cl["cls"] == "no_capacity").sum())),
        check("without county code, projects (all states; after dropping <= 0)", EXPECTED["no_county_n"],
              int(len(no_fips_all))),
        check("without county code, MW", EXPECTED["no_county_mw"], round(float(no_fips_all["poi_mw"].sum()), 3), tol=0.05),
        check("Connecticut, projects", EXPECTED["ct_n"], int(len(ct_all))),
        check("Connecticut, MW", EXPECTED["ct_mw"], round(float(ct_all["poi_mw"].sum()), 3), tol=0.05),
        check("outside the 49 units or no state, projects", EXPECTED["outside_n"], int(len(outside))),
        check("outside the 49 units or no state, MW", EXPECTED["outside_mw"], round(float(outside["poi_mw"].sum()), 3), tol=0.05),
        check("capacity <= 0, projects", EXPECTED["nonpos_n"], int(len(nonpos))),
        check("capacity <= 0, MW", EXPECTED["nonpos_mw"], round(float(nonpos["poi_mw"].sum()), 3), tol=0.05),
        check("state field != state of county code, projects", EXPECTED["mismatch_n"], int(len(cross)),
              note="listed below with MW; each goes to the state of field 'state', and to the county by its code"),
        check("the five listed in SPEC r5 2.7 are the ones found", "5 of 5",
              f"{len(MISMATCH_IDS_SPEC & cross_ids)} of 5"),
        check("max |residual| of state_reconciliation", 0, max_resid, tol=1e-6),
    ]
    report = {
        "layer": LAYER, "layer_id": LAYER_ID, "snapshot_date": snap, "states": scope.mode, "identity": identity,
        "identity_state_prev": identity_state, "checks": checks,
        "numbers": {
            "county_sum_mw_recomputed": round(float(rec["queue_mw_active"].sum()), 3),
            "excluded_nonpositive_in_counties": int(bad.sum()),
            "ct_records_old_codes": int(len(ct_old)), "ct_records_new_codes": int(len(ct_new)),
            "crosswalk_applied": recoded,
            "county_side_records_with_other_state_field": int(len(c_side)),
        },
        "lists": {
            "state_field_differs_from_county_code": rows(cross),
            "county_side_state_field_elsewhere_or_outside": rows(c_side),
            "nonpositive": rows(nonpos),
        },
        "inputs": inputs,
    }

    meta = {
        "source": "Berkeley Lab (LBNL) 'Queued Up' - interconnection queue database",
        "source_url": "https://emp.lbl.gov/queues",
        "vintage": "Queued Up 2026 edition (data through 2025-12-31)",
        "license": "CC BY 4.0 (confirmed for the Queued Up 2026 edition)",
        "coverage": "48 states + DC (the 49 units); Alaska and Hawaii not_covered",
        "edition": "Queued Up 2026", "current_through": "2025-12-31",
        "rule": "q_status == 'active'; capacity = max(mw1, mw2, mw3); capacity <= 0 left out; "
                "state = field 'state' (only the 49 codes count)",
        "county_rule_keys_restored_from_legacy_meta": ["--crosswalk", "--ct-not-covered", "--drop-nonpositive"],
        "code_crosswalk": {"file": str(crosswalk), "applied": recoded},
        "n_units_covered": 49, "n_units_not_covered": 2,
        "excluded_nonpositive": rows(nonpos),
        "known_gaps": (
            f"{len(outside)} active records have no state or a state outside the 49 units "
            f"({float(outside['poi_mw'].sum()):.1f} MW) and are not in the layer. "
            f"{len(nonpos)} records with capacity <= 0 are left out ({float(nonpos['poi_mw'].sum()):.1f} MW). "
            f"The state values include {len(no_fips_all)} projects without a county code "
            f"({float(no_fips_all['poi_mw'].sum()):.1f} MW) and {len(ct_all)} Connecticut projects "
            f"({float(ct_all['poi_mw'].sum()):.1f} MW); county values have neither. "
            f"{len(cross)} records carry a county code of another state than their 'state' field: "
            "they count in the state of the field and in the county of the code. "
            "Factual draft; wording by [RES]7."
        ),
        "inputs": inputs, "boundary_file": str(C.BOUNDARY_SHP),
        "identity_with_release_0_1_0": identity,
    }
    meta["alaska_hawaii"] = ("not_covered: the source has no record of either state (0 records with state AK/HI, "
                             "0 county codes 02xxx/15xxx, all statuses); empty values, not zero")
    csv_path = C.write_layer_csv(LAYER, out, meta, snap)

    tbl = counties[["fips", "NAME", "NAMELSAD"]].merge(
        rec.reset_index()[["fips", "queue_mw_active", "n_active_projects", "coverage_status", "coverage_note"]],
        on="fips", how="left")
    county_meta = C.read_legacy_meta(LEGACY_META)
    county_meta.update({
        "states_mode": scope.mode,
        "rebuilt_for": "abf-layers 0.3.0 (SPEC_USA_AKHI_v0_3_0 r2); county rule unchanged; Alaska and Hawaii "
                       "counties are not in this table: the source does not cover them (not_covered by the frame)",
        "boundary_file": str(C.BOUNDARY_SHP), "boundary_file_sha256": inputs["county_shp.shp"]["sha256"],
        "input": str(xlsx), "identity_with_release_0_1_0": identity,
    })
    county_csv = C.write_county_table("queue_lbnl", tbl, county_meta, snap)
    report["county_table"] = {"file": county_csv.name, "rows": int(len(tbl)),
                              "text_vs_legacy": C.compare_text_to_legacy(county_csv, C.OUTPUT_DIR / LEGACY_TABLE)}
    C.assert_inputs_unchanged(inputs, input_paths)
    C.write_part(LAYER, snap, report, recon)
    log.info("DONE. %s ; %s", csv_path, county_csv)
    C.stop_if_failed(checks, LAYER)


if __name__ == "__main__":
    main()
