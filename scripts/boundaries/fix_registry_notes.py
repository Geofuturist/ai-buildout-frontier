#!/usr/bin/env python3
"""
fix_registry_notes.py -- one-off correction of the text columns of boundaries/boundary_registry.csv before the
v0.2.0 build (SPEC_BND_boundaries_v0_2_0.md r4 S2.7 p.10-11; table of RES_texts_BND_v0_2_0.md S5 p.2).

Run (from the repo root, BEFORE build_boundaries.py; dry run unless --write):
    python scripts\\boundaries\\fix_registry_notes.py --registry boundaries\\boundary_registry.csv --report registry_notes_report.csv
    python scripts\\boundaries\\fix_registry_notes.py --registry boundaries\\boundary_registry.csv --report registry_notes_report.csv --write

Rules (all checked, a failure stops the script and writes nothing):
  - only `notes` changes (and `verified_against` of GRC, SPEC p.11); 20 countries: GTM, IND, ZAF, ITA; AUS, BEL,
    ESP, GIN, LKA, TTO; ATG, BRB, DMA, LIE, MLT, NRU, SMR, WSM; RUS; GRC;
  - each old text is found in its cell exactly once;
  - every other column of every row of the file, and every untouched line, is byte-for-byte as before (compared);
  - report: country - column - was - now (printed, and to --report as csv).
The script is one-shot: after --write the old texts are gone, so a second run stops with "old text not found".
Greece: the fallback texts of SPEC p.11 (ISO 3166-2 GR-69 only) are used; the reference to Art. 105 of the
Constitution of Greece is for the next version of the registry.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

P4B = "(rule P4b); independent check required"
P4B_NEW = "(rule P4b); confirmed by the verification sample"
UNIT_TYPE_CORE = "unit type from VER official source"

# (iso3, column, old, new);  old=None -> the unit-type remark (position handled in code)
REPL = [
    ("GTM", "notes", P4B, P4B_NEW),
    ("IND", "notes", P4B, P4B_NEW),
    ("ZAF", "notes", P4B, P4B_NEW),
    ("ITA", "notes",
     "(rule P4b); independent check required | unit type from VER official source | units without a reference code follow NE field 'region' (rule P7c via P6); field choice to be confirmed by the official source",
     "(rule P4b); confirmed by the verification sample | units without a reference code follow NE field 'region' (rule P7c via P6); confirmed by the official list (ISTAT)"),
    ("GRC", "notes", "(rule P4b); independent check required | Mount Athos", "(rule P4b) | Mount Athos"),
    ("GRC", "verified_against", "verdict disputed; the verification sample",
     "verdict disputed (Mount Athos is not a region in this list); dispute resolved by ISO 3166-2 GR-69 (CLDR gr69); the verification sample"),
    ("RUS", "notes", "are not units of RUS here.",
     "are not units of RUS here; Crimea and Sevastopol are listed in the contested_areas layer."),
] + [(i, "notes", None, "") for i in ("AUS", "BEL", "ESP", "GIN", "LKA", "TTO")] \
  + [(i, "notes", "Administrative-centre check not possible for units this small",
      "Administrative-center check not possible for units this small")
     for i in ("ATG", "BRB", "DMA", "LIE", "MLT", "NRU", "SMR", "WSM")]


def fail(msg: str):
    sys.exit(f"STOP: {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", required=True, type=Path)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = args.registry.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    rows_before = list(csv.reader(io.StringIO(raw)))
    header = rows_before[0]
    col = {name: i for i, name in enumerate(header)}
    for need in ("iso3", "level", "notes", "verified_against"):
        if need not in col:
            fail(f"column {need!r} not found")

    # work on parsed rows to find/replace inside the cell (exactly once), then re-serialise ONLY the touched lines
    new_rows = [list(r) for r in rows_before]
    report = []
    touched_idx: set[int] = set()
    for iso3, column, old, new in REPL:
        hits = [i for i, r in enumerate(new_rows) if i > 0 and r[col["iso3"]] == iso3 and r[col["level"]] == "ADM1"]
        if len(hits) != 1:
            fail(f"{iso3}: {len(hits)} ADM1 rows in the registry")
        i = hits[0]
        cell = new_rows[i][col[column]]
        if old is None:  # the unit-type remark: at the start, in the middle (" | " before) or the whole cell
            if cell.count(UNIT_TYPE_CORE) != 1:
                fail(f"{iso3}: unit-type remark found {cell.count(UNIT_TYPE_CORE)} times in {column}")
            if cell == UNIT_TYPE_CORE:
                res = ""
            elif cell.startswith(UNIT_TYPE_CORE + " | "):
                res = cell[len(UNIT_TYPE_CORE) + 3:]
            elif cell.endswith(" | " + UNIT_TYPE_CORE):
                res = cell[: -(len(UNIT_TYPE_CORE) + 3)]
            elif cell.count(" | " + UNIT_TYPE_CORE + " | ") == 1:
                res = cell.replace(" | " + UNIT_TYPE_CORE + " | ", " | ", 1)
            else:
                fail(f"{iso3}: unexpected position of the unit-type remark")
        else:
            if cell.count(old) != 1:
                fail(f"{iso3}: old text found {cell.count(old)} times in {column}: {old!r}")
            res = cell.replace(old, new, 1)
        new_rows[i][col[column]] = res
        touched_idx.add(i)
        report.append((iso3, column, cell, res))

    # text-level substitution inside the physical line of the row: the original quoting of every touched row stays as it
    # was, untouched lines are not rewritten at all. One logical row == one physical line (no embedded newlines).
    if len(lines) and lines[-1] == "":
        body = lines[:-1]; tail = [""]
    else:
        body = lines; tail = []
    if len(body) != len(rows_before):
        fail(f"physical lines ({len(body)}) != csv rows ({len(rows_before)}): embedded newlines, not supported")
    out_lines = list(body)
    for iso3, column, was, now in report:
        i = next(k for k, r in enumerate(rows_before) if k > 0 and r[col["iso3"]] == iso3 and r[col["level"]] == "ADM1")
        if '"' in was or '"' in now:
            fail(f"{iso3}: double quote inside the cell, not supported")
        if out_lines[i].count(was) != 1:
            fail(f"{iso3}: the cell text is found {out_lines[i].count(was)} times in its line")
        quoted = ('"' + was + '"') in out_lines[i] or (was.count(",") > 0)
        if ("," in now) and not quoted:
            fail(f"{iso3}: the new text has a comma but the cell is not quoted")
        out_lines[i] = out_lines[i].replace(was, now, 1)
    out = nl.join(out_lines + tail)

    # ---- comparison: everything but the intended cells is unchanged ----
    after = list(csv.reader(io.StringIO(out)))
    if len(after) != len(rows_before):
        fail("row count changed")
    allowed = {(c_, col[cn]) for c_, cn in [(iso, cn) for iso, cn, _, _ in REPL]}  # (iso3, column index)
    n_cells = 0
    for i, (b, a) in enumerate(zip(rows_before, after)):
        if b == a:
            continue
        iso3 = b[col["iso3"]]
        for j in range(len(b)):
            if b[j] != a[j]:
                if (iso3, j) not in allowed or b[col["level"]] != "ADM1":
                    fail(f"unexpected change: row {iso3}, column {header[j]}")
                n_cells += 1
    n_untouched_same = sum(1 for i, (x, y) in enumerate(zip(out_lines, body)) if i not in touched_idx and x == y)
    if n_untouched_same != len(body) - len(touched_idx):
        fail("an untouched line differs")
    print(f"OK: {len(rows_before) - 1} registry rows; {len(touched_idx)} rows changed, {n_cells} cells; "
          f"{len(body) - len(touched_idx)} other lines byte-for-byte unchanged; header unchanged: {rows_before[0] == after[0]}")

    print("\ncountry | column | was | now")
    for iso3, column, was, now in report:
        print(f"{iso3} | {column} | {was} | {now}")
    if args.report:
        with open(args.report, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["iso3", "column", "was", "now"])
            w.writerows(report)
        print(f"\nreport: {args.report}")
    if args.write:
        args.registry.write_bytes(out.encode("utf-8"))
        print(f"written: {args.registry}")
    else:
        print("\ndry run (add --write to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
