r"""abf-dc 0.2.0: compare the output of the first run of the data step with the rerun (ARCH7 24.10, item 7).

Run command (from the repository root, Windows; the old folder is the copy that V made before the rerun):
    python scripts\dc\compare_rerun_v020.py --old "D:\GISData\AI\DC\out\abf-dc-v0.2.0_run1" --new "D:\GISData\AI\DC\out\abf-dc-v0.2.0"

Expected:
  dc_atlas_count_usa_adm2.csv  differs only in coverage_note, in exactly 17 rows (the not covered units)
  dc_atlas_count_places.csv    the old columns are the same, in the same order, with the same values; new columns after power_class:
                               type_group, n_type_colocation ... n_type_other
  county_records.csv           byte-identical
  operator_type_groups.csv     new file (LF)
Exit code 0 when all of this holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

NEW_COLS = ["type_group", "n_type_colocation", "n_type_telecom", "n_type_developer_investor", "n_type_cloud",
            "n_type_enterprise_it", "n_type_ai_compute", "n_type_other"]


def read(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def compare(old: Path, new: Path) -> list[str]:
    bad: list[str] = []
    ok = []
    # counties
    a, b = read(old / "dc_atlas_count_usa_adm2.csv"), read(new / "dc_atlas_count_usa_adm2.csv")
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        bad.append("dc_atlas_count_usa_adm2.csv: columns or number of rows differ")
    else:
        diff_cols = [c for c in a.columns if not a[c].equals(b[c])]
        if diff_cols != ["coverage_note"]:
            bad.append(f"dc_atlas_count_usa_adm2.csv: columns that differ: {diff_cols} (expected only coverage_note)")
        else:
            n = int((a["coverage_note"] != b["coverage_note"]).sum())
            if n != 17:
                bad.append(f"dc_atlas_count_usa_adm2.csv: coverage_note differs in {n} rows (expected 17)")
            elif (a.loc[a["coverage_note"] != b["coverage_note"], "coverage_status"] != "not_covered").any():
                bad.append("dc_atlas_count_usa_adm2.csv: coverage_note changed in a covered row")
            else:
                ok.append("dc_atlas_count_usa_adm2.csv: only coverage_note changed, in 17 rows of units that are not covered")
    # places
    a, b = read(old / "dc_atlas_count_places.csv"), read(new / "dc_atlas_count_places.csv")
    old_cols = list(a.columns)
    if list(b.columns) != old_cols + NEW_COLS:
        bad.append(f"dc_atlas_count_places.csv: columns {list(b.columns)} (expected the old ones plus {NEW_COLS})")
    elif len(a) != len(b) or not a.equals(b[old_cols]):
        bad.append("dc_atlas_count_places.csv: values of the old columns differ")
    else:
        ok.append(f"dc_atlas_count_places.csv: the {len(old_cols)} old columns are the same, {len(NEW_COLS)} new columns after power_class")
    # county_records and the groups table
    if (old / "county_records.csv").read_bytes() != (new / "county_records.csv").read_bytes():
        bad.append("county_records.csv: bytes differ")
    else:
        ok.append("county_records.csv: identical")
    g = new / "operator_type_groups.csv"
    if not g.exists():
        bad.append("operator_type_groups.csv: not in the new folder")
    elif b"\r" in g.read_bytes():
        bad.append("operator_type_groups.csv: CRLF line ends")
    else:
        ok.append("operator_type_groups.csv: present, LF")
    for line in ok:
        print("OK   ", line)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    bad = compare(Path(a.old), Path(a.new))
    for line in bad:
        print("STOP ", line)
    print("\nAll as expected." if not bad else f"\n{len(bad)} differences from the expected.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
