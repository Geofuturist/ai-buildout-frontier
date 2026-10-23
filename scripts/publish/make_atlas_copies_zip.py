r"""Pack the copies of the Atlas tables into one zip that is the same byte for byte on every run (abf-dc, Q6 of SPEC_DC r7).

Run command (from the repository root, Windows):
    python scripts\publish\make_atlas_copies_zip.py --src "D:\GISData\AI\DC\abf-scratch-dc\research\dc_world\inputs\atlas_copies" --out "D:\GISData\AI\DC\release_inputs\atlas_copies_20261014-18.zip" --expect-files 38

What it does: puts every file of --src (not its subfolders) into the zip under its own file name, exactly as it is
(bytes are not touched). The zip is deterministic: files in the order of their names, fixed date 1980-01-01 in every
entry, no compression (so the bytes do not depend on the version of zlib), fixed file attributes. Packing twice, on
any computer, gives the same SHA-256. The script packs the files twice into a temporary place, compares, and only
then writes --out. It prints the list of files and the SHA-256 of the zip.
Exit code: 0 done, 2 the folder is missing or empty or the count does not match --expect-files.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def pack(src_files: list[Path], dst: Path) -> None:
    """Write the zip: stored, fixed dates and attributes, files sorted by name."""
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path in sorted(src_files, key=lambda p: p.name.encode("utf-8")):
            info = zipfile.ZipInfo(path.name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3                 # unix, whatever the computer
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.flag_bits = 0
            zf.writestr(info, path.read_bytes())


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic zip of the Atlas table copies.")
    ap.add_argument("--src", required=True, type=Path, help="folder with the copies (atlas_copies)")
    ap.add_argument("--out", required=True, type=Path, help="zip file to write")
    ap.add_argument("--expect-files", type=int, default=None, help="stop if the folder holds another number of files")
    a = ap.parse_args()
    if not a.src.is_dir():
        print(f"STOP: folder not found: {a.src}")
        return 2
    files = [p for p in a.src.iterdir() if p.is_file()]
    if not files:
        print(f"STOP: no files in {a.src}")
        return 2
    if a.expect_files is not None and len(files) != a.expect_files:
        print(f"STOP: {len(files)} files in {a.src}, expected {a.expect_files}")
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp1, tmp2 = a.out.with_name(a.out.name + ".try1"), a.out.with_name(a.out.name + ".try2")
    try:
        pack(files, tmp1)
        pack(files, tmp2)
        h1, h2 = sha256_of(tmp1), sha256_of(tmp2)
        if h1 != h2:
            print("STOP: two packings of the same files differ; nothing is written")
            return 2
        tmp1.replace(a.out)
    finally:
        for t in (tmp1, tmp2):
            if t.exists():
                t.unlink()
    total = sum(p.stat().st_size for p in files)
    for p in sorted(files, key=lambda p: p.name.encode("utf-8")):
        print(f"  {p.name}\t{p.stat().st_size}")
    print(f"files: {len(files)}, bytes inside: {total}, zip bytes: {a.out.stat().st_size}")
    print(f"zip: {a.out}")
    print(f"sha256: {h1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
