r"""Check that the values of the layers kept from an earlier release did not change, and write the result into the report.

Run command (from the repository root, Windows):
    python scripts\publish\compare_release_values.py "D:\GISData\release\abf-fra-v0.1.0" "D:\GISData\release\abf-fra-v0.2.0"
    python scripts\publish\compare_release_values.py "D:\GISData\release\abf-layers-v0.1.0" "D:\GISData\release\abf-layers-v0.2.0" --allow-added-columns coverage_note

For every layer that is in both folders it compares
  - the CSV file: same columns in the same order, same rows, every value equal as written (text comparison); with
    --allow-added-columns the new file may have the listed extra columns (empty for covered units, given for not_covered);
  - the GeoParquet file: the same geometry of every row;
  - the layer meta file: the list of text paths that differ (listed for review, not a stop).
The result is written as a section "Comparison with <old release>" into release_report.md of the NEW folder
(an earlier section of the same name is replaced). Exit code 1 if any value or geometry differs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

KEY_CANDIDATES = ("unit_id", "record_id")


def flatten(obj: Any, path: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{path}[{i}]"))
    else:
        out[path] = obj
    return out


def compare_csv(old: Path, new: Path, allow_added: tuple[str, ...] = ()) -> list[str]:
    """Text comparison of two CSV files. `allow_added`: columns that the new file may have in addition (abf-layers 0.2.0:
    coverage_note). The columns of the old file must stay in the same order with equal values; an added column must be
    empty in every covered row and given in every not_covered row."""
    a = pd.read_csv(old, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    b = pd.read_csv(new, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    problems: list[str] = []
    added = [c for c in b.columns if c in allow_added and c not in a.columns]
    b_kept = b.drop(columns=added)
    if list(a.columns) != list(b_kept.columns):
        return [f"columns differ: {list(a.columns)} vs {list(b.columns)}"]
    if added:
        if "coverage_status" not in b.columns:
            return [f"added columns {added} need coverage_status in the new file"]
        for col in added:
            cov = b["coverage_status"] == "covered"
            if (b.loc[cov, col] != "").any():
                problems.append(f"added column {col} is not empty in {int((b.loc[cov, col] != '').sum())} covered rows")
            if (b.loc[~cov, col] == "").any():
                problems.append(f"added column {col} is empty in {int((b.loc[~cov, col] == '').sum())} not_covered rows")
        b = b_kept
    key = next((k for k in KEY_CANDIDATES if k in a.columns), None)
    if key is None:
        return ["no key column (unit_id or record_id)"]
    a = a.set_index(key).sort_index()
    b = b.set_index(key).sort_index()
    only_a, only_b = sorted(set(a.index) - set(b.index)), sorted(set(b.index) - set(a.index))
    if only_a:
        problems.append(f"{len(only_a)} rows only in the old release: {only_a[:5]}")
    if only_b:
        problems.append(f"{len(only_b)} rows only in the new release: {only_b[:5]}")
    common = a.index.intersection(b.index)
    diff = a.loc[common] != b.loc[common]
    n_cells = int(diff.to_numpy().sum())
    if n_cells:
        problems.append(f"{n_cells} values differ in {int(diff.any(axis=1).sum())} rows")
        shown = 0
        for col in a.columns:
            for k in diff.index[diff[col]]:
                problems.append(f"  {key}={k} {col}: {a.at[k, col]!r} -> {b.at[k, col]!r}")
                shown += 1
                if shown >= 10:
                    break
            if shown >= 10:
                break
    return problems


def compare_geometry(old: Path, new: Path) -> list[str]:
    a, b = gpd.read_parquet(old), gpd.read_parquet(new)
    key = next((k for k in KEY_CANDIDATES if k in a.columns), None)
    if key is None or key not in b.columns:
        return ["no key column for geometry comparison"]
    a, b = a.set_index(key).sort_index(), b.set_index(key).sort_index()
    if list(a.index) != list(b.index):
        return ["rows differ in the GeoParquet file"]
    wa = a.geometry.apply(lambda g: g.wkb if g is not None else b"")
    wb = b.geometry.apply(lambda g: g.wkb if g is not None else b"")
    bad = list(a.index[(wa != wb).to_numpy()])
    return [f"{len(bad)} geometries differ: {bad[:5]}"] if bad else []


def compare_meta(old: Path, new: Path) -> list[str]:
    fa, fb = flatten(json.loads(old.read_text(encoding="utf-8"))), flatten(json.loads(new.read_text(encoding="utf-8")))
    changed = sorted(p for p in set(fa) | set(fb) if fa.get(p) != fb.get(p))
    # a path with an index is shown without the index; release and freshness always differ
    short = sorted({re.sub(r"\[\d+\]", "[]", p) for p in changed})
    return short


def main(argv: list[str]) -> int:
    allow_added: tuple[str, ...] = ()
    if "--allow-added-columns" in argv:
        i = argv.index("--allow-added-columns")
        allow_added = tuple(c for c in argv[i + 1].split(",") if c) if i + 1 < len(argv) else ()
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 3 or (allow_added == () and "--allow-added-columns" in sys.argv):
        print(__doc__)
        return 2
    old_dir, new_dir = Path(argv[1]), Path(argv[2])
    for d in (old_dir, new_dir):
        if not d.is_dir():
            print(f"STOP: folder not found: {d}")
            return 2
    old_name = old_dir.name
    ids = sorted(p.name[: -len(".meta.json")] for p in old_dir.glob("*.meta.json")
                 if (new_dir / p.name).exists())
    if not ids:
        print("STOP: no layer is in both folders")
        return 2
    lines = [f"## Comparison with {old_name}", ""]
    failed = False
    for lid in ids:
        res = {
            "csv": compare_csv(old_dir / f"{lid}.csv", new_dir / f"{lid}.csv", allow_added),
            "geometry": compare_geometry(old_dir / f"{lid}.parquet", new_dir / f"{lid}.parquet"),
        }
        bad = any(res.values())
        failed |= bad
        lines.append(f"- {lid}: " + ("**DIFFERENT**" if bad else "values and geometry identical"))
        for kind, probs in res.items():
            for p in probs:
                lines.append(f"  - {kind}: {p}")
        meta_diff = compare_meta(old_dir / f"{lid}.meta.json", new_dir / f"{lid}.meta.json")
        lines.append("  - meta paths that differ (for review): " + (", ".join(meta_diff) if meta_diff else "none"))
    only_new = sorted(p.name[: -len(".meta.json")] for p in new_dir.glob("*.meta.json")
                      if not (old_dir / p.name).exists())
    lines += ["", f"Layers only in the new release: {', '.join(only_new) if only_new else 'none'}", ""]
    print("\n".join(l for l in lines if not l.startswith("  - meta paths")))
    report = new_dir / "release_report.md"
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    text = re.sub(rf"\n?## Comparison with {re.escape(old_name)}\n.*?(?=\n## |\Z)", "", text, flags=re.S)
    report.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines), encoding="utf-8", newline="\n")
    print(f"\nWritten into {report}")
    if failed:
        print("STOP: values of layers kept from the old release changed")
        return 1
    print("OK: values and geometry of the kept layers are identical")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
