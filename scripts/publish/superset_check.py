r"""Cross-check `rows_superset` (abf-layers 0.3.0, SPEC_USA_AKHI_v0_3_0 r2 section 4a item 2).

The layer of segments of 0.3.0 has all the segments of the earlier release and new ones (the lines of Alaska and Hawaii).
The check proves it from the files of the two release folders:

  1. the earlier release folder is the published one (SHA-256 of its GeoParquet file equals the record of its manifest.json,
     when the manifest is there);
  2. both GeoParquet files have the same columns, the key column is unique in both;
  3. every key of the earlier layer is in the new layer, with the same value in every column and the same geometry
     (coordinates equal within `geometry_tolerance_deg`, default 1e-9 degrees);
  4. the number of new rows equals `expected_added` (counted, not compared), and the earlier file has `expected_old` rows,
     when these are given.

yaml (in cross_checks of the release):
    - kind: rows_superset
      layer: energy_transmission_lines_hifld
      key: record_id
      old_release_dir: 'D:\GISData\release\abf-layers-v0.2.0'
      expected_old: 93880
      expected_added: 349

A failure is a stop (G9). `compare_subset` is also used by compare_release_values.py (--allow-added-rows).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from common import GateError, Report, resolve_path, sha256_file

DEFAULT_TOLERANCE = 1e-9


def compare_subset(old_path: Path, new_path: Path, key: str, tolerance: float = DEFAULT_TOLERANCE) -> tuple[list[str], int, int]:
    """GeoParquet files: the rows of `old_path` are in `new_path` with equal values and geometry.
    -> (problems, rows of the old file, rows only in the new file)."""
    a, b = gpd.read_parquet(old_path), gpd.read_parquet(new_path)
    problems: list[str] = []
    if list(a.columns) != list(b.columns):
        return [f"columns differ: {list(a.columns)} vs {list(b.columns)}"], len(a), 0
    for name, df in (("earlier", a), ("new", b)):
        if key not in df.columns:
            return [f"key column {key} is not in the {name} file"], len(a), 0
        dup = int(df[key].duplicated().sum())
        if dup:
            problems.append(f"{dup} repeated {key} in the {name} file")
    if problems:
        return problems, len(a), 0
    a, b = a.set_index(key), b.set_index(key)
    missing = a.index.difference(b.index)
    if len(missing):
        problems.append(f"{len(missing)} rows of the earlier file are not in the new file: {list(missing[:5])}")
    common = a.index.intersection(b.index)
    ac, bc = a.loc[common], b.loc[common]
    geom_name = a.geometry.name
    for col in a.columns:
        if col == geom_name:
            ga = np.array(ac.geometry.values, dtype=object)
            gb = np.array(bc.geometry.values, dtype=object)
            same = shapely.equals_exact(ga, gb, tolerance=tolerance)
            same = np.asarray(same) | (pd.isna(ga) & pd.isna(gb))
            n = int((~same).sum())
        else:
            n = int((~((ac[col] == bc[col]) | (ac[col].isna() & bc[col].isna()))).sum())
        if n:
            shown = ac.index[(~same) if col == geom_name else ~((ac[col] == bc[col]) | (ac[col].isna() & bc[col].isna()))][:3]
            problems.append(f"{n} values differ in {col}, for example {key} {list(shown)}")
    return problems, len(a), len(b.index.difference(a.index))


def check_rows_superset(chk: dict[str, Any], out: Path, report: Report) -> None:
    layer, key = chk["layer"], chk["key"]
    old_dir = resolve_path(chk["old_release_dir"])
    old = old_dir / f"{layer}.parquet"
    new = out / f"{layer}.parquet"
    for p in (old, new):
        if not p.exists():
            raise GateError("G9", f"rows_superset: {p} not found")
    manifest = old_dir / "manifest.json"
    if manifest.exists():
        mf = json.loads(manifest.read_text(encoding="utf-8"))
        rec = next((lay["files"].get("parquet") for lay in mf.get("layers", []) if lay.get("layer_id") == layer), None)
        if rec and sha256_file(old) != rec["sha256"]:
            raise GateError("G9", f"rows_superset: {old} is not the published file of {mf.get('tag')} (SHA-256 differs from its manifest)")
        checked = f"SHA-256 of the earlier file equals its manifest ({mf.get('tag')})"
    else:
        checked = "the earlier release folder has no manifest.json, its file was not tied to the published SHA-256"
    problems, n_old, n_added = compare_subset(old, new, key, float(chk.get("geometry_tolerance_deg", DEFAULT_TOLERANCE)))
    if "expected_old" in chk and n_old != int(chk["expected_old"]):
        problems.append(f"the earlier file has {n_old} rows, expected {chk['expected_old']}")
    if "expected_added" in chk and n_added != int(chk["expected_added"]):
        problems.append(f"{n_added} rows are new, expected {chk['expected_added']}")
    if problems:
        raise GateError("G9", f"rows_superset {layer}: " + "; ".join(problems[:6]))
    report.section(f"Layer {layer} against the earlier release", [
        f"- the {n_old:,} segments of {old_dir.name} are in this release with equal values and geometry "
        f"(tolerance {chk.get('geometry_tolerance_deg', DEFAULT_TOLERANCE)} degrees)",
        f"- {n_added:,} segments are new (counted; expected {chk.get('expected_added', 'not given')})",
        f"- {checked}",
    ])
    report.note(f"rows_superset: {layer} has the {n_old:,} earlier segments unchanged and {n_added:,} new")
