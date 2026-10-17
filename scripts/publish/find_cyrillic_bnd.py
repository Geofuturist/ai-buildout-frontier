r"""Read-only: find Cyrillic in the reference files of abf-boundaries and compare the old registry rows with git.

Run command (from the repository root, Windows):
    python scripts\publish\find_cyrillic_bnd.py > cyrillic_bnd.txt

Changes nothing. It looks at the files of the repository that are published as reference files (boundaries\*.csv,
holes_whitelist.geojson) and at validation_report.json and unit_hashes.csv of the CODE-BND output. For every cell with
Cyrillic it prints file, line, iso3/level or first column, column name and the text around. For the registry it also
says which rows differ from the committed version (git HEAD) and shows whether the committed rows have Cyrillic.
"""
from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from pathlib import Path

CYR = re.compile("[\u0400-\u04FF]")
REPO_FILES = ["boundary_registry.csv", "adm0_overrides.csv", "adm0_patches.csv", "name_overrides.csv", "contested_areas.csv",
              "adm1_plan.csv", "adm1_leftovers.csv", "code_overrides.csv", "holes_whitelist.geojson"]
BND_DIR = Path(r"D:\GISData\Boundaries\out\abf-boundaries-v0.2.0")


def scan_csv(path: Path) -> int:
    n = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head = rows[0] if rows else []
    for ln, row in enumerate(rows[1:], start=2):
        for col, val in zip(head, row):
            m = CYR.search(val)
            if m:
                n += 1
                print(f"  {path.name} line {ln} [{row[0]} {row[1] if len(row) > 1 else ''}] column {col}: ...{val[max(0, m.start() - 40):m.start() + 40]}...")
    return n


def scan_text(path: Path) -> int:
    n = 0
    for ln, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        m = CYR.search(line)
        if m:
            n += 1
            print(f"  {path.name} line {ln}: ...{line[max(0, m.start() - 40):m.start() + 40]}...")
    return n


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")   # a redirected cp1251 console cannot print accented letters
    total = 0
    print("== Cyrillic in reference files")
    for name in REPO_FILES:
        p = Path("boundaries") / name
        if not p.exists():
            print(f"  {name}: missing"); continue
        k = scan_csv(p) if p.suffix == ".csv" else scan_text(p)
        total += k
        print(f"{name}: {k} place(s)")
    for name in ("validation_report.json", "unit_hashes.csv"):
        p = BND_DIR / name
        if p.exists():
            k = scan_text(p); total += k; print(f"{name} (CODE-BND output): {k} place(s)")
    print("\n== boundary_registry.csv against git HEAD")
    r = subprocess.run(["git", "show", "HEAD:boundaries/boundary_registry.csv"], capture_output=True)
    if r.returncode:
        print("  git show failed:", r.stderr.decode("utf-8", "replace")[:200])
    else:
        old = list(csv.DictReader(io.StringIO(r.stdout.decode("utf-8-sig"))))
        new = list(csv.DictReader(Path("boundaries/boundary_registry.csv").open(encoding="utf-8-sig", newline="")))
        key = lambda x: (x["iso3"], x["level"])
        newmap = {key(x): x for x in new}
        print(f"  committed rows: {len(old)}, working rows: {len(new)}")
        for o in old:
            nw = newmap.get(key(o))
            if nw is None:
                print(f"  {key(o)}: row is missing in the working file"); continue
            diff = [c for c in o if o[c] != nw.get(c)]
            cyr_old = [c for c in o if CYR.search(o[c])]
            print(f"  {key(o)}: differs in columns {diff or 'none'}; Cyrillic in committed row: {cyr_old or 'none'}")
    print("\nTOTAL cells/lines with Cyrillic:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
