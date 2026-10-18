r"""Restore the 7 rows of version 0.1.0 in boundaries\boundary_registry.csv byte for byte (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\patch_registry_frozen_v020.py            # shows what would change, writes nothing
    python scripts\publish\patch_registry_frozen_v020.py --apply    # writes the file

Why (ARCH6, 17 October): the 7 rows of version 0.1.0 (USA ADM1/ADM2, FRA ADM1/ADM2, GBR ADM1, NOR ADM1/ADM2) must be
identical to commit 227ce5c of 9 October, from which abf-boundaries v0.1.0 was built. The reference copy is
releases\reference\boundary_registry_abf-boundaries-v0.1.0.csv (the file of that commit). Every one of the 7 rows of the
registry that differs from the reference is replaced by the reference row as a whole. The other rows are kept byte for
byte, the line endings of the file too. If a row of the reference is missing in the registry, nothing is written.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry_rows import has_bom, read_records  # noqa: E402

PATH = Path("boundaries") / "boundary_registry.csv"
REFERENCE = Path("releases") / "reference" / "boundary_registry_abf-boundaries-v0.1.0.csv"


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    for p in (PATH, REFERENCE):
        if not p.exists():
            print(f"STOP: {p} not found; run from the repository root")
            return 2
    nl, header, records = read_records(PATH)
    _, ref_header, ref_records = read_records(REFERENCE)
    if header != ref_header:
        print("STOP: the header of the registry differs from the reference header")
        return 2
    ref = {k: (norm, cells) for k, norm, cells, _ in ref_records}
    present = [k for k, *_ in records]
    missing = [k for k in ref if present.count(k) != 1]
    if missing:
        print(f"STOP: these rows are missing or duplicated in the registry: {missing}")
        return 2
    out: list[str] = []
    changed = 0
    for key, norm, cells, orig in records:
        if key not in ref or norm == ref[key][0]:
            out.append(orig)
            continue
        ref_norm, ref_cells = ref[key]
        changed += 1
        print(f"  {key}: row replaced by the row of commit 227ce5c")
        for col, a, b in zip(header, cells, ref_cells):
            if a != b:
                print(f"    {col}:\n      was: {a[:100]}\n      now: {b[:100]}")
        eol = orig[len(orig.rstrip("\r\n")):]
        out.append(ref_norm.replace("\n", nl) + eol)
    if not changed:
        print("Nothing to change: the 7 rows equal the reference.")
        return 0
    # the header line is kept from the file: rebuild the text as header chunk + records
    raw = PATH.read_bytes().decode("utf-8")
    body = raw[1:] if raw.startswith("﻿") else raw
    first_len = len(body.splitlines(keepends=True)[0])
    result = ("﻿" if has_bom(PATH) else "") + body[:first_len] + "".join(out)
    print(f"{changed} row(s) replaced.")
    if apply:
        PATH.write_bytes(result.encode("utf-8"))
        print(f"Written {PATH}")
    else:
        print("Not written (run again with --apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
