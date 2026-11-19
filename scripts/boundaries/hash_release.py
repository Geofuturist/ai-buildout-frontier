"""hash_release.py -- read-only: SHA-256 of every file of a release folder (for the hand-off).

Run (from the repo root):
    python scripts\\boundaries\\hash_release.py --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.3.0"

Writes release_sha256.txt (one line per file: sha256, size in bytes, relative path) into --out-dir, and prints it.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    root = args.out_dir
    lines = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name == "release_sha256.txt":
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        lines.append(f"{h.hexdigest()}  {p.stat().st_size:>12}  {p.relative_to(root).as_posix()}")
    text = "\n".join(lines)
    (root / "release_sha256.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
