r"""Set the DOI and the publication date in a release yaml (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\set_release_doi.py releases\abf-boundaries-v0.2.0.yaml 10.5281/zenodo.NNNNNNN 2026-10-20

Only the lines `doi:` and `published_at:` at column 0 are changed; the rest of the file is kept.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DOI_REGEX = re.compile(r"^10\.5281/zenodo\.\d+$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    path, doi, date = Path(argv[1]), argv[2], argv[3]
    if not path.exists():
        print(f"STOP: file not found: {path}")
        return 2
    if not DOI_REGEX.match(doi):
        print(f"STOP: DOI must look like 10.5281/zenodo.1234567, got {doi!r}")
        return 2
    if not DATE_REGEX.match(date):
        print(f"STOP: date must look like 2026-10-20, got {date!r}")
        return 2
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    wanted = {"doi": doi, "published_at": f'"{date}"'}
    changed = False
    for key, value in wanted.items():
        hits = [i for i, ln in enumerate(lines) if re.match(rf"^{key}\s*:", ln)]
        if len(hits) != 1:
            print(f"STOP: expected one line `{key}:` at column 0, found {len(hits)}")
            return 2
        new = f"{key}: {value}"
        if lines[hits[0]] != new:
            print(f"{key}: {lines[hits[0]]!r} -> {new!r}")
            lines[hits[0]] = new
            changed = True
    if changed:
        path.write_bytes(nl.join(lines).encode("utf-8"))
        print(f"Written {path}")
    else:
        print("Nothing to change.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
