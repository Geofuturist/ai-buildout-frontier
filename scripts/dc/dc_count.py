r"""abf-dc: country count `dc_atlas_count_adm0` and `groups.csv` (SPEC_DC_world_v0_1_0 r2, section 2.6). Not run on its own.

All 242 ADM0 units of the frame, counted by iso3_source (like US states, ADR section 11), not by points.
Coverage: the 126 countries of the Atlas "National" list are copied; a country outside the list is `covered` with 0 (decision V, mc-0002).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from dc_lib import BuildStop

STATUS_COLS = {"Operating / Construction": "n_operating_or_construction", "Planned": "n_planned", "Retired": "n_retired"}
CLASS_COLS = {"lt10": "n_class_lt10", "10_99": "n_class_10_99", "100_999": "n_class_100_999", "ge1000": "n_class_ge1000", "": "n_class_unknown"}
VALUE_COLS = ["n_records", *STATUS_COLS.values(), *CLASS_COLS.values()]


def count_table(atl: pd.DataFrame, adm0: pd.DataFrame, listed_iso3: set[str], retired_not_copied: set[str], special_notes: dict[str, str],
                expected_total: int) -> pd.DataFrame:
    rows = []
    for r in adm0.sort_values("unit_id").itertuples(index=False):
        sub = atl[atl["iso3_source"] == r.iso3]
        row = dict(unit_id=r.unit_id, name=r.name, coverage_status="covered")
        notes = []
        if r.iso3 not in listed_iso3:
            notes.append("Country is not in the Atlas National list (126); no records (manual_checks mc-0002).")
        if r.iso3 in special_notes:
            notes.append(special_notes[r.iso3])
        if r.iso3 in retired_not_copied:
            notes.append("Retired records not copied for this country.")
        row["coverage_note"] = " ".join(notes)
        row["n_records"] = len(sub)
        for st, col in STATUS_COLS.items():
            row[col] = "" if (col == "n_retired" and r.iso3 in retired_not_copied) else int((sub["status_raw"] == st).sum())
        for cl, col in CLASS_COLS.items():
            row[col] = int((sub["power_class"] == cl).sum())
        rows.append(row)
    df = pd.DataFrame(rows, columns=["unit_id", "name", "coverage_status", "coverage_note", *VALUE_COLS])
    if len(df) != 242:
        raise BuildStop(f"{len(df)} ADM0 units in the count table, expected 242")
    if int(df["n_records"].sum()) != expected_total:
        raise BuildStop(f"sum of n_records over ADM0 is {int(df['n_records'].sum())}, expected {expected_total}")
    return df


def group_table(groups_csv: Path, counts: pd.DataFrame) -> pd.DataFrame:
    """One row per group: members, members_checked / not_checked, aggregate_state and the count columns summed over members.
    A member is `checked` when its ADM0 count row is `covered`."""
    by_iso = counts.set_index("unit_id")
    groups: dict[str, list[str]] = {}
    for r in csv.DictReader(open(groups_csv, encoding="utf-8-sig", newline="")):
        groups.setdefault(r["group_id"], []).append(r["member_iso3"])
    rows = []
    for gid, members in groups.items():
        missing = [m for m in members if m not in by_iso.index]
        if missing:
            raise BuildStop(f"group {gid}: members not in the frame: {missing}")
        checked = [m for m in members if by_iso.at[m, "coverage_status"] == "covered"]
        row = dict(group_id=gid, members=len(members), members_checked=len(checked), members_not_checked=len(members) - len(checked),
                   aggregate_state="complete" if len(checked) == len(members) else "partial")
        sub = counts[counts["unit_id"].isin(members)]
        for c in VALUE_COLS:
            vals = pd.to_numeric(sub[c], errors="coerce")
            row[c] = int(vals.sum())
            if c == "n_retired" and sub[c].astype(str).eq("").any():
                row[c] = ""              # the sum would be understated: a member has no retired records copied
        rows.append(row)
    return pd.DataFrame(rows)
