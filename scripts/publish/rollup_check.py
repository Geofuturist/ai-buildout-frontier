r"""Cross-check `rollup_sums` (abf-layers 0.2.0, SPEC_USA_states_v0_2_0 section 3 item 5).

A state layer and the county layer of the same source, both in the release folder, and the reference file
state_reconciliation.csv. For every state and every field of the reference file the check proves:

  1. state_value equals the value of the published state CSV;
  2. county_sum equals the sum of the published county CSV (the counties of that state, by unit_id);
  3. difference = state_value - county_sum;
  4. the residual is 0 (the column `within_tolerance` must be True where the file has it, as for km: rounding only);
     for km fields also |state - county sum| <= 0.5 km x the number of covered counties of the state;
  5. demand (`peak_fields`): the largest county peak <= the state peak <= the sum of the county peaks, and the largest
     county peak of the file equals that of the published county CSV;
  6. `max_fields` / `any_fields` (transmission): the state value is the largest / the "any" of its counties.

Every state of the state layer that is covered must have a row for every field; no row may name another unit.
A failure is a stop (G4). The check does not read anything outside the release folder.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from common import GateError, Report

COUNTY_PREFIX = "USA-2-"
STATE_PREFIX = "USA-1-"


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _county_tol(values: pd.Series, n: int) -> float:
    """Tolerance for a sum of published (rounded) county values: exact for whole numbers."""
    v = values.dropna()
    if len(v) and ((v - v.round()).abs() < 1e-9).all():
        return 1e-6
    return 0.06 + 0.005 * n


def check_rollup_sums(chk: dict[str, Any], out: Path, report: Report) -> None:
    ref_name = chk["file"]
    ref = pd.read_csv(out / ref_name, dtype=str, keep_default_na=False)
    problems: list[str] = []
    lines: list[str] = []
    for pair in chk["pairs"]:
        sl, cl = pair["state_layer"], pair["county_layer"]
        st = pd.read_csv(out / f"{sl}.csv", dtype=str, keep_default_na=False)
        co = pd.read_csv(out / f"{cl}.csv", dtype=str, keep_default_na=False)
        covered_states = st[st["coverage_status"] == "covered"]["unit_id"].tolist()
        co = co[co["coverage_status"] == "covered"].copy()
        co["_state"] = STATE_PREFIX + co["unit_id"].str[len(COUNTY_PREFIX):len(COUNTY_PREFIX) + 2]
        rows = ref[ref["layer_id"] == sl]
        fields = list(pair["fields"])
        n_checked = 0
        stray = sorted(set(rows["unit_id"]) - set(covered_states))
        if stray:
            problems.append(f"{ref_name}: rows of {sl} name units that are not covered states: {stray[:5]}")
        extra_fields = sorted(set(rows["field"]) - set(fields))
        if extra_fields:
            problems.append(f"{ref_name}: rows of {sl} for fields the check does not list: {extra_fields}")
        peak = set(pair.get("peak_fields") or [])
        for fld in fields:
            sub = rows[rows["field"] == fld].set_index("unit_id")
            missing = sorted(set(covered_states) - set(sub.index))
            if missing or sub.index.duplicated().any():
                problems.append(f"{ref_name}: {sl}.{fld} must have exactly one row per covered state; missing {missing[:5]}, "
                                f"duplicates {sorted(set(sub.index[sub.index.duplicated()]))[:5]}")
                continue
            st_val = _num(st.set_index("unit_id")[fld])
            co_val = _num(co[fld])
            by_state = co_val.groupby(co["_state"])
            n_cov = co.groupby("_state").size()
            for uid in covered_states:
                r = sub.loc[uid]
                sv, cs, diff = float(r["state_value"]), float(r["county_sum"]), float(r["difference"])
                n = int(n_cov.get(uid, 0))
                tol = _county_tol(co_val, n)
                where = f"{sl}.{fld} {uid}"
                if abs(sv - float(st_val[uid])) > 0.011 and abs(sv - float(st_val[uid])) > 1e-9 * abs(sv):
                    problems.append(f"{where}: state value {sv} in {ref_name} differs from the published {st_val[uid]}")
                real_sum = float(by_state.sum().get(uid, 0.0))
                if abs(cs - real_sum) > tol:
                    problems.append(f"{where}: county_sum {cs} in {ref_name} differs from the sum of the published county values {real_sum:.4f}")
                if abs(diff - (sv - cs)) > 0.11:
                    problems.append(f"{where}: difference {diff} is not state value minus county_sum ({sv - cs:.4f})")
                if fld in peak:
                    mx = float(r["nrel_max_county_peak_mw"])
                    real_mx = float(co_val[co["_state"] == uid].max())
                    if abs(mx - real_mx) > 1e-3:
                        problems.append(f"{where}: largest county peak {mx} in {ref_name} differs from the published counties {real_mx}")
                    if not (mx <= sv + 1e-6 and sv <= real_sum + tol):
                        problems.append(f"{where}: peak order broken: largest county peak {mx}, state peak {sv}, sum of county peaks {real_sum:.3f}")
                else:
                    resid = r.get("residual", "")
                    within = r.get("within_tolerance", "")
                    if within != "":
                        if within != "True":
                            problems.append(f"{where}: difference {diff} is outside the rounding tolerance")
                        if abs(sv - real_sum) > 0.5 * n + 1e-6:
                            problems.append(f"{where}: |state {sv} - county sum {real_sum:.1f}| > 0.5 km x {n} counties")
                    elif resid != "" and abs(float(resid)) > 0.011:
                        problems.append(f"{where}: residual {resid} is not 0")
                    elif resid == "":
                        problems.append(f"{where}: no residual in {ref_name}")
                n_checked += 1
        for fld in pair.get("max_fields") or []:
            sv = _num(st.set_index("unit_id")[fld])
            cv = _num(co[fld]).groupby(co["_state"]).max()
            for uid in covered_states:
                if abs(float(sv[uid]) - float(cv.get(uid, float("nan")))) > 1e-6:
                    problems.append(f"{sl}.{fld} {uid}: {sv[uid]} is not the largest county value {cv.get(uid)}")
        for fld in pair.get("any_fields") or []:
            sv = st.set_index("unit_id")[fld]
            cv = co[fld].isin(["True", "true"]).groupby(co["_state"]).any()
            for uid in covered_states:
                if (sv[uid] in ("True", "true")) != bool(cv.get(uid, False)):
                    problems.append(f"{sl}.{fld} {uid}: {sv[uid]} does not match 'any county' ({bool(cv.get(uid, False))})")
        lines.append(f"- {sl} against {cl}: {n_checked} state-field rows ({len(covered_states)} states x {len(fields)} fields)")
    report.section(f"Cross-check rollup_sums ({ref_name})", lines + [f"- problems: {len(problems)}"])
    if problems:
        raise GateError("G4", f"rollup_sums: {len(problems)} problems, for example: " + "; ".join(problems[:5]))
    report.note(f"cross-check rollup_sums: {sum(len(p['fields']) for p in chk['pairs'])} fields of {len(chk['pairs'])} state layers "
                f"equal the county layers and {ref_name}")
