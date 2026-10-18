#!/usr/bin/env python3
"""
apply_crimea_to_rus.py -- one-off edit of the inputs of the v0.2.0 build for the rule of de facto control
(SPEC_BND_boundaries_v0_2_0.md r6 S2.9; texts and codes: RES_texts_BND_v0_2_0.md r4 S6).

What it changes (three files in boundaries/; adm0_patches.csv and contested_areas.csv are edited by hand/by [RES]):
  1. adm1_plan.csv       -- two rows: UKR-1-40 / UKR-1-43 become RUS-1-67 / RUS-1-35 (country, unit_id, code, match_via,
                            cldr_code empty). The plan differs from abf-scratch `adm1-triage` @ f877a30 in exactly these two rows.
  2. boundary_registry.csv -- RUS|ADM1: code_scheme, expected_units 83 -> 85, notes, verified_against (appended);
                            UKR|ADM1: expected_units 27 -> 25, notes.
  3. code_overrides.csv  -- two new columns `unit_code`, `code_scheme` (empty for the old rows) and two rows
                            (Crimea: OKATO 35, Sevastopol: OKATO 67) after the last RUS row.

Run from the repo root, BEFORE build_boundaries.py. Dry run unless --write:
    python scripts\\boundaries\\apply_crimea_to_rus.py --boundaries-dir boundaries --report crimea_edit_report.csv
    python scripts\\boundaries\\apply_crimea_to_rus.py --boundaries-dir boundaries --report crimea_edit_report.csv --write

Rules (a failure stops the script and writes nothing):
  - every old line / old cell is found exactly once and equals the expected old text;
  - every other line of every file is byte-for-byte as before; in a touched registry line every other cell is
    byte-for-byte as before (the line is split into raw cells, only the named cells are replaced);
  - the files are read back and compared as tables (rows, columns, cell by cell) with the intended changes only;
  - report: file - row - column - was - now (printed, and to --report as csv).
One-shot: after --write the old texts are gone, so a second run stops with "old ... not found".
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

# ---------------------------------------------------------------- 1. plan
PLAN_OLD_NEW = [
    ("UKR,UKR-1-40,40,Sevastopol,RUS-5482,ne_as_is,own,ua40",
     "RUS,RUS-1-67,67,Sevastopol,RUS-5482,ne_as_is,national_code_okato,"),
    ("UKR,UKR-1-43,43,Crimea,RUS-283,ne_as_is,own,ua43",
     "RUS,RUS-1-35,35,Crimea,RUS-283,ne_as_is,national_code_okato,"),
]

# ---------------------------------------------------------------- 2. registry  (iso3, column, old cell, new cell)
RUS_VA_SUFFIX = ("; Republic of Crimea and Sevastopol: Constitution of the Russian Federation, Art. 65(1) (same document); "
                 "codes 35 and 67 from the OKATO classifier (Rosstat open data 7708234640-okato, file "
                 "data-20260801T1408-structure-20140709T1807.csv, version of 2026-08-01), downloaded by human:V on "
                 "2026-10-18, extracted by script")
RUS_NOTES_OLD = ("Part of ADM0 without ADM1 (rule P7b): (unnamed) [RU-X01~] 37.9 km2 (0.00% of country), small island at 68.79 N, "
                 "67.28 E inside ADM0 RUS, touches only Yamal-Nenets; not disputed | The Constitution of the Russian Federation "
                 "lists 89 subjects; six of them lie in Ukraine under the U.S. point of view used by these boundaries and are "
                 "not units of RUS here; Crimea and Sevastopol are listed in the contested_areas layer. | P8: 1 nested unit(s), "
                 "listed in the nested-units table")
RUS_NOTES_NEW = ("Part of ADM0 without ADM1 (rule P7b): (unnamed) [RU-X01~] 37.9 km2 (0.00% of country), small island at 68.79 N, "
                 "67.28 E inside ADM0 RUS, touches only Yamal-Nenets; not disputed | The Constitution of the Russian Federation, "
                 "Art. 65(1), lists 89 subjects. 85 are units of RUS here: 83 from ISO 3166-2, and the Republic of Crimea "
                 "(RUS-1-35) and Sevastopol (RUS-1-67), shown under Russia by the project's rule of de facto control, with OKATO "
                 "codes because ISO 3166-2 lists them under Ukraine (UA-43, UA-40); Ukraine's claim is in the contested_areas "
                 "layer (CA-0001, CA-0002). The four subjects that the Constitution lists for the Donetsk, Luhansk, Zaporizhzhia "
                 "and Kherson regions are not units of RUS here: the rule applies only to whole units, and no open dated line of "
                 "control was found, so the frame keeps these regions under Ukraine. | P8: 1 nested unit(s), listed in the "
                 "nested-units table")
UKR_NOTES_OLD = "P8: 1 nested unit(s), listed in the nested-units table"
UKR_NOTES_NEW = ("ISO 3166-2 lists 27 top-level subdivisions of Ukraine; 25 are units of UKR here. The Autonomous Republic of "
                 "Crimea (UA-43) and Sevastopol (UA-40) are shown under Russia by the project's rule of de facto control, as "
                 "RUS-1-35 and RUS-1-67; Ukraine's claim is in the contested_areas layer (CA-0001, CA-0002). The Donetsk, "
                 "Luhansk, Zaporizhzhia and Kherson regions (UKR-1-14, UKR-1-09, UKR-1-23, UKR-1-65) are units of UKR in full, "
                 "although Russia has controlled parts of them since 2022: the rule applies only to whole units, and no open "
                 "dated line of control was found. | P8: 1 nested unit(s), listed in the nested-units table")
CODE_SCHEME_OLD = "ISO 3166-2 via Unicode CLDR release-48-2"
CODE_SCHEME_NEW = "ISO 3166-2 via Unicode CLDR release-48-2; OKATO for RUS-1-35 and RUS-1-67"
REG_EDITS = [
    ("RUS", "code_scheme", CODE_SCHEME_OLD, CODE_SCHEME_NEW),
    ("RUS", "expected_units", "83", "85"),
    ("RUS", "notes", RUS_NOTES_OLD, RUS_NOTES_NEW),
    ("RUS", "verified_against", None, None),   # old + RUS_VA_SUFFIX (old read from the file, must end the cell as expected)
    ("UKR", "expected_units", "27", "25"),
    ("UKR", "notes", UKR_NOTES_OLD, UKR_NOTES_NEW),
]
RUS_VA_OLD_END = "the verification sample covers countries whose official lists could be retrieved"

# ---------------------------------------------------------------- 3. code_overrides
CO_NEW_COLS = ["unit_code", "code_scheme"]
_SRC = ("Rosstat open data 7708234640-okato, file data-20260801T1408-structure-20140709T1807.csv, saved by human:V "
        "2026-10-18, extracted by script")
CO_ROWS = [
    ["RUS", "UA-43", "", "RUS-283", "national_code",
     f"Republic of Crimea: OKATO 35 ({_SRC}); a subject of the Russian Federation by its Constitution, Art. 65(1); shown "
     f"under Russia by the de facto control rule; ISO 3166-2 lists it under Ukraine as UA-43",
     "V 2026-10-18 (SPEC_BND r6 §2.9); code extracted by RES 2026-10-18", "35", "OKATO"],
    ["RUS", "UA-40", "", "RUS-5482", "national_code",
     f"Sevastopol: OKATO 67 ({_SRC}); a subject of the Russian Federation by its Constitution, Art. 65(1); shown under "
     f"Russia by the de facto control rule; ISO 3166-2 lists it under Ukraine as UA-40",
     "V 2026-10-18 (SPEC_BND r6 §2.9); code extracted by RES 2026-10-18", "67", "OKATO"],
]


def fail(msg: str):
    sys.exit(f"STOP: {msg}")


def read_lines(path: Path):
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    tail = [""] if lines and lines[-1] == "" else []
    body = lines[:-1] if tail else lines
    return raw, nl, body, tail


def rows_of(text: str):
    return list(csv.reader(io.StringIO(text)))


def split_raw(line: str):
    """Split one physical CSV line into raw cell strings (quotes kept). No embedded newlines."""
    cells, cur, inq, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if inq:
            cur.append(ch)
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('"'); i += 1
                else:
                    inq = False
        else:
            if ch == '"':
                inq = True; cur.append(ch)
            elif ch == ",":
                cells.append("".join(cur)); cur = []
            else:
                cur.append(ch)
        i += 1
    cells.append("".join(cur))
    return cells


def ser(value: str) -> str:
    if any(ch in value for ch in ',"\n\r'):
        return '"' + value.replace('"', '""') + '"'
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    bd: Path = args.boundaries_dir
    report: list[tuple[str, str, str, str, str]] = []   # file, row, column, was, now
    outputs: dict[Path, str] = {}

    # ---- 1. plan: whole-line replacement
    pth = bd / "adm1_plan.csv"
    raw, nl, body, tail = read_lines(pth)
    out = list(body)
    for old, new in PLAN_OLD_NEW:
        if body.count(old) != 1:
            fail(f"adm1_plan.csv: old line not found exactly once (found {body.count(old)}): {old!r}")
        k = out.index(old)
        out[k] = new
        report.append(("adm1_plan.csv", new.split(",")[1], "(row)", old, new))
    new_text = nl.join(out + tail)
    before_t, after_t = rows_of(raw), rows_of(new_text)
    if len(before_t) != len(after_t) or before_t[0] != after_t[0]:
        fail("adm1_plan.csv: row count or header changed")
    n_diff = sum(1 for a, b in zip(before_t, after_t) if a != b)
    if n_diff != len(PLAN_OLD_NEW):
        fail(f"adm1_plan.csv: {n_diff} rows differ, expected {len(PLAN_OLD_NEW)}")
    outputs[pth] = new_text

    # ---- 2. registry: raw-cell replacement in the touched lines
    pth = bd / "boundary_registry.csv"
    raw, nl, body, tail = read_lines(pth)
    table = rows_of(raw)
    if len(table) != len(body):
        fail("boundary_registry.csv: physical lines != csv rows (embedded newlines are not supported)")
    header = table[0]
    col = {n: i for i, n in enumerate(header)}
    out = list(body)
    for iso3, column, old, new in REG_EDITS:
        hits = [i for i, r in enumerate(table) if i > 0 and r[col["iso3"]] == iso3 and r[col["level"]] == "ADM1"]
        if len(hits) != 1:
            fail(f"{iso3}: {len(hits)} ADM1 rows in the registry")
        i = hits[0]
        cells = split_raw(out[i])
        if len(cells) != len(header):
            fail(f"{iso3}: raw split gives {len(cells)} cells, header has {len(header)}")
        parsed = rows_of(out[i])[0]
        j = col[column]
        if parsed[j] != rows_of(",".join(cells))[0][j] or [rows_of(c_)[0][0] if c_ else "" for c_ in cells] != parsed:
            fail(f"{iso3}: raw split does not reproduce the parsed row")
        cur = parsed[j]
        if column == "verified_against":
            if not cur.endswith(RUS_VA_OLD_END):
                fail(f"{iso3}: verified_against does not end as expected")
            new = cur + RUS_VA_SUFFIX
            old = cur
        elif cur != old:
            fail(f"{iso3}: {column}: the cell is not the expected old text. Found: {cur!r}")
        cells[j] = ser(new)
        out[i] = ",".join(cells)
        report.append(("boundary_registry.csv", f"{iso3}|ADM1", column, old, new))
    new_text = nl.join(out + tail)
    after = rows_of(new_text)
    allowed = {(iso3, col[cn]) for iso3, cn, _, _ in REG_EDITS}
    n_cells = 0
    if len(after) != len(table) or after[0] != table[0]:
        fail("boundary_registry.csv: row count or header changed")
    for b, a in zip(table, after):
        for j in range(len(b)):
            if b[j] != a[j]:
                if (b[col["iso3"]], j) not in allowed or b[col["level"]] != "ADM1":
                    fail(f"boundary_registry.csv: unexpected change in {b[col['iso3']]}, column {header[j]}")
                n_cells += 1
    if n_cells != len(REG_EDITS):
        fail(f"boundary_registry.csv: {n_cells} cells differ, expected {len(REG_EDITS)}")
    touched = {next(i for i, r in enumerate(table) if i > 0 and r[col['iso3']] == e[0] and r[col['level']] == 'ADM1') for e in REG_EDITS}
    if any(out[i] != body[i] for i in range(len(body)) if i not in touched):
        fail("boundary_registry.csv: an untouched line differs")
    outputs[pth] = new_text

    # ---- 3. code_overrides: two columns, two rows
    pth = bd / "code_overrides.csv"
    raw, nl, body, tail = read_lines(pth)
    table = rows_of(raw)
    if len(table) != len(body):
        fail("code_overrides.csv: physical lines != csv rows")
    if table[0][-len(CO_NEW_COLS):] == CO_NEW_COLS:
        fail("code_overrides.csv: the new columns are already there (old ... not found)")
    if any(len(r) != len(table[0]) for r in table):
        fail("code_overrides.csv: rows of different length")
    out = [body[0] + "," + ",".join(CO_NEW_COLS)] + [ln + ",," for ln in body[1:]]
    last_rus = max(i for i, r in enumerate(table) if i > 0 and r[0] == "RUS")
    new_lines = [",".join(ser(v) for v in r) for r in CO_ROWS]
    out = out[: last_rus + 1] + new_lines + out[last_rus + 1:]
    new_text = nl.join(out + tail)
    after = rows_of(new_text)
    if len(after) != len(table) + len(CO_ROWS) or any(len(r) != len(table[0]) + len(CO_NEW_COLS) for r in after):
        fail("code_overrides.csv: unexpected shape after the edit")
    old_back = [r[: len(table[0])] for r in after if r not in [[*x] for x in CO_ROWS] and r[0] != "iso3"]
    if old_back != [r for r in table[1:]]:
        fail("code_overrides.csv: old rows changed")
    report.append(("code_overrides.csv", "(header)", "columns", ",".join(table[0]), ",".join(table[0] + CO_NEW_COLS)))
    for r in CO_ROWS:
        report.append(("code_overrides.csv", f"{r[0]}|{r[1]}", "(new row)", "", ",".join(r)))
    outputs[pth] = new_text

    print(f"OK: plan 2 rows; registry {len(REG_EDITS)} cells in 2 rows; code_overrides +2 columns +{len(CO_ROWS)} rows. "
          f"All other lines/cells unchanged (compared).")
    print("\nfile | row | column | was | now")
    for f, r, cn, was, now in report:
        print(f"{f} | {r} | {cn} | {was} | {now}")
    if args.report:
        with open(args.report, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["file", "row", "column", "was", "now"])
            w.writerows(report)
        print(f"\nreport: {args.report}")
    if args.write:
        for p, t in outputs.items():
            p.write_bytes(t.encode("utf-8"))
            print(f"written: {p}")
    else:
        print("\ndry run (add --write to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
