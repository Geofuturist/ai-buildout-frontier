r"""Idempotent patch of releases/abf-layers-v0.2.0.yaml: adds boundaries.name_overrides.

Usage (from the repository root):
    python scripts\publish\patch_release_v020_names.py
Safe to run again: if the key is already there, nothing changes. Line endings are kept.
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("releases") / "abf-layers-v0.2.0.yaml"
KEY = "name_overrides:"
LINE = "  name_overrides: 'boundaries\\name_overrides.csv'"


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found; run this from the repository root")
        return 1
    raw = TARGET.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    if any(l.strip().startswith(KEY) for l in lines):
        print(f"{TARGET}: name_overrides is already set, nothing changed")
        return 0
    idx = next((i for i, l in enumerate(lines) if l.strip().startswith("registry:")), None)
    if idx is None:
        print(f"ERROR: no 'registry:' line under boundaries: in {TARGET}; nothing changed")
        return 1
    lines.insert(idx + 1, LINE)
    TARGET.write_bytes(eol.join(lines).encode("utf-8"))
    print(f"{TARGET}: added boundaries.name_overrides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
