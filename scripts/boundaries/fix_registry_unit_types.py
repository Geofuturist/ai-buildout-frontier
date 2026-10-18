#!/usr/bin/env python3
"""
fix_registry_unit_types.py -- one-off edit of boundaries/boundary_registry.csv after the transfer of Crimea and
Sevastopol from UKR to RUS (SPEC_BND_boundaries_v0_2_0.md r7 S2.9 p.8, decision of [ARCH6] 18.10).

What it changes (two rows of the registry, three cells):
  1. UKR|ADM1 unit_type_local, unit_type_en -- recomputed: the distinct values of the NE admin-1 fields `type` and
     `type_en` of the 25 units that UKR has now, sorted, joined with "/", empty values dropped. This is how the old
     strings were made: the script first reproduces the old strings from the 27 old units and stops if it cannot.
     Result: "Autonomous Republic", "Federal City", "Gorod Federalnogo Znacheniya" and "Oblast" leave UKR.
  2. RUS|ADM1 verified_by -- "; human:V" appended (the OKATO file was downloaded by V).
  The RUS unit types are NOT changed (decision of [ARCH6]); the script prints what a recomputation would give.

Run from the repo root, BEFORE build_boundaries.py. Dry run unless --write:
    python scripts\\boundaries\\fix_registry_unit_types.py --boundaries-dir boundaries --sources-dir "D:\\GISData\\Boundaries\\sources" --report unit_types_report.csv
    python scripts\\boundaries\\fix_registry_unit_types.py --boundaries-dir boundaries --sources-dir "D:\\GISData\\Boundaries\\sources" --report unit_types_report.csv --write

Rules (a failure stops the script and writes nothing): every old cell equals the expected old text; every other line of
the file is byte-for-byte as before and every other cell of the touched lines too (compared); the file is read back and
compared cell by cell. One-shot: after --write the old texts are gone, so a second run stops.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
from apply_crimea_to_rus import fail, read_lines, rows_of, ser, split_raw  # noqa: E402

OLD_UKR_LOCAL = "Gorod Federalnogo Znacheniya/Oblast/Oblast'/Rada"
OLD_UKR_EN = "Autonomous Republic/Federal City/Municipality/Region"
OLD_RUS_VERIFIED_BY = "script:p4_01_classify.py; agent:ver-adm1"
NEW_RUS_VERIFIED_BY = OLD_RUS_VERIFIED_BY + "; human:V"
CRIMEA_SEVASTOPOL_NE = ["RUS-283", "RUS-5482"]


def distinct_types(ne: pd.DataFrame, ne_codes: list[str]) -> tuple[str, str]:
    sub = ne[ne["adm1_code"].isin(ne_codes)]
    if len(sub) != len(set(ne_codes)):
        fail(f"NE admin-1: {len(sub)} objects found for {len(set(ne_codes))} codes")
    out = []
    for col in ("type", "type_en"):
        out.append("/".join(sorted({v for v in sub[col].fillna("") if v})))
    return out[0], out[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    manifest = json.loads((args.sources_dir / "sources_manifest.json").read_text(encoding="utf-8"))
    ne = gpd.read_file(manifest["ne_adm1"]["path"])
    ne = pd.DataFrame(ne.drop(columns="geometry"))
    plan = pd.read_csv(args.boundaries_dir / "adm1_plan.csv", dtype=str, keep_default_na=False)

    def plan_codes(iso3: str) -> list[str]:
        return [x.strip() for s in plan[plan["iso3"] == iso3]["ne_adm1_codes"] for x in s.split(";")]

    ukr_now = plan_codes("UKR")
    if len(ukr_now) != 25 or set(ukr_now) & set(CRIMEA_SEVASTOPOL_NE):
        fail(f"adm1_plan.csv: UKR has {len(ukr_now)} units / still has Crimea or Sevastopol -- run apply_crimea_to_rus.py first")
    # the method must reproduce the old strings from the old set of 27 units
    old_local, old_en = distinct_types(ne, ukr_now + CRIMEA_SEVASTOPOL_NE)
    if (old_local, old_en) != (OLD_UKR_LOCAL, OLD_UKR_EN):
        fail(f"the method does not reproduce the old UKR strings: got {old_local!r} / {old_en!r}")
    new_local, new_en = distinct_types(ne, ukr_now)
    rus_local, rus_en = distinct_types(ne, plan_codes("RUS"))

    pth = args.boundaries_dir / "boundary_registry.csv"
    raw, nl, body, tail = read_lines(pth)
    table = rows_of(raw)
    if len(table) != len(body):
        fail("boundary_registry.csv: physical lines != csv rows (embedded newlines are not supported)")
    header = table[0]
    col = {n: i for i, n in enumerate(header)}
    edits = [
        ("UKR", "unit_type_local", OLD_UKR_LOCAL, new_local),
        ("UKR", "unit_type_en", OLD_UKR_EN, new_en),
        ("RUS", "verified_by", OLD_RUS_VERIFIED_BY, NEW_RUS_VERIFIED_BY),
    ]
    out = list(body)
    report = []
    touched = set()
    for iso3, column, old, new in edits:
        hits = [i for i, r in enumerate(table) if i > 0 and r[col["iso3"]] == iso3 and r[col["level"]] == "ADM1"]
        if len(hits) != 1:
            fail(f"{iso3}: {len(hits)} ADM1 rows in the registry")
        i = hits[0]
        cells = split_raw(out[i])
        parsed = rows_of(body[i])[0]
        if len(cells) != len(header) or parsed != table[i]:
            fail(f"{iso3}: raw split does not reproduce the parsed row")
        j = col[column]
        if parsed[j] != old or rows_of(out[i])[0][j] != old:
            fail(f"{iso3}: {column}: the cell is not the expected old text. Found: {parsed[j]!r}")
        cells[j] = ser(new)
        out[i] = ",".join(cells)
        touched.add(i)
        report.append(("boundary_registry.csv", f"{iso3}|ADM1", column, old, new))

    new_text = nl.join(out + tail)
    after = rows_of(new_text)
    allowed = {(iso3, col[cn]) for iso3, cn, _, _ in edits}
    if len(after) != len(table) or after[0] != table[0]:
        fail("row count or header changed")
    n_cells = 0
    for b, a in zip(table, after):
        for j in range(len(b)):
            if b[j] != a[j]:
                if (b[col["iso3"]], j) not in allowed or b[col["level"]] != "ADM1":
                    fail(f"unexpected change in {b[col['iso3']]}, column {header[j]}")
                n_cells += 1
    if n_cells != len(edits) or any(out[i] != body[i] for i in range(len(body)) if i not in touched):
        fail("an untouched cell or line differs")

    print(f"OK: 3 cells in 2 registry rows; {len(body) - len(touched)} other lines byte-for-byte unchanged.")
    print("\nfile | row | column | was | now")
    for f, r, cn, was, now in report:
        print(f"{f} | {r} | {cn} | {was} | {now}")
    cur_rus = next(r for r in table[1:] if r[col["iso3"]] == "RUS" and r[col["level"]] == "ADM1")
    print(f"\nRUS unit types are NOT changed (decision of ARCH6). Registry: {cur_rus[col['unit_type_local']]!r} / "
          f"{cur_rus[col['unit_type_en']]!r}; a recomputation over the 85 RUS units would give: {rus_local!r} / {rus_en!r}")
    if args.report:
        with open(args.report, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["file", "row", "column", "was", "now"])
            w.writerows(report)
        print(f"\nreport: {args.report}")
    if args.write:
        pth.write_bytes(new_text.encode("utf-8"))
        print(f"written: {pth}")
    else:
        print("\ndry run (add --write to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
