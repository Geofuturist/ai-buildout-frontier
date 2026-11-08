r"""
adm1_common.py
==============
Helper module for the four ADM1 (state) builders of abf-layers 0.2.0
(SPEC_USA_states_v0_2_0 r5). NOT RUN DIRECTLY.

Put it in the same folder as gci_conus_common.py (scripts\conus\). It imports
gci_conus_common.py without changing it (SPEC r5 section 2.7).

Import order matters: this module sets the default county-shapefile path
(ABF_COUNTY_SHP) BEFORE gci_conus_common reads it, so every builder must
`import adm1_common` first.
"""

from __future__ import annotations

import os

# Same county file that built the 0.1.0 layers (meta: boundary_file). The user
# can still override it with the ABF_COUNTY_SHP environment variable.
os.environ.setdefault(
    "ABF_COUNTY_SHP",
    r"D:\GISData\AI\Administrative units\USA\cb_2023_us_county_500k\cb_2023_us_county_500k.shp",
)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Iterable, Optional  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gci_conus_common import (  # noqa: E402,F401
    BOUNDARY_SHP,
    CONUS_STATES_FIPS,
    CONUS_STATES_USPS,
    JOIN_CRS,
    OUTPUT_DIR,
    load_conus_counties,
    log,
    resolve_points_to_counties,
    safe_float,
)

REPO = OUTPUT_DIR.parent.parent  # ...\AI Buildup Frontier project
RELEASE_DIR = REPO / "data" / "abf-layers" / "v0.1.0"
UNITS_CSV = REPO / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
FLOAT_TOL = 1e-6  # SPEC 2.1 item 5: numbers to 1e-6, integers exactly


# ------------------------------------------------------------------ arguments
def base_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "--snapshot-date",
        default=dt.date.today().strftime("%Y%m%d"),
        help="date tag of the output files, YYYYMMDD (default: today). "
        "Use the same value for all four builders and for finish_adm1_report.py.",
    )
    return ap


# ------------------------------------------------------------------ boundaries
def usps_to_fips() -> dict[str, str]:
    """Postal code -> state FIPS, from STUSPS/STATEFP of the county file (SPEC 2.1 item 3)."""
    import pyogrio

    df = pyogrio.read_dataframe(BOUNDARY_SHP, read_geometry=False, columns=["STATEFP", "STUSPS"])
    pairs = df.drop_duplicates()
    mapping = {r.STUSPS: r.STATEFP for r in pairs.itertuples() if r.STATEFP in CONUS_STATES_FIPS}
    if len(mapping) != 49 or set(mapping) != set(CONUS_STATES_USPS):
        raise RuntimeError(f"STUSPS->STATEFP map is not the expected 49 units: {len(mapping)}")
    return mapping


def state_units() -> pd.DataFrame:
    """The 51 USA ADM1 rows from units.csv of abf-boundaries v0.2.0; 49 covered (no AK 02, HI 15)."""
    u = pd.read_csv(UNITS_CSV, dtype=str)
    s = u[u["unit_id"].str.startswith("USA-1-")][["unit_id"]].copy()
    s["state_fips"] = s["unit_id"].str[-2:]
    s["covered"] = s["state_fips"].isin(CONUS_STATES_FIPS)
    if len(s) != 51 or int(s["covered"].sum()) != 49:
        raise RuntimeError(f"units.csv: expected 51 USA-1-* rows / 49 covered, got {len(s)} / {int(s['covered'].sum())}")
    return s.sort_values("state_fips").reset_index(drop=True)


# ------------------------------------------------------------------ hashing
def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def shp_files(shp: Path, label: str) -> dict[str, Path]:
    """The four parts of a shapefile hashed separately: .shp .dbf .shx .prj (SPEC r5 2.7)."""
    out: dict[str, Path] = {}
    for ext in (".shp", ".dbf", ".shx", ".prj"):
        p = Path(shp).with_suffix(ext)
        if p.exists():
            out[f"{label}{ext}"] = p
        else:
            log.warning("Shapefile part missing, not hashed: %s", p)
    return out


def hash_inputs(paths: dict[str, Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for label, p in paths.items():
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"Input not found: {p}")
        log.info("SHA-256: %s", p.name)
        out[label] = {"path": str(p), "size": p.stat().st_size, "sha256": sha256_file(p)}
    return out


def assert_inputs_unchanged(before: dict[str, dict], paths: dict[str, Path]) -> dict[str, dict]:
    """Second hash at the end of the build (as in 0.1.0 check input_sha256): must match."""
    after = hash_inputs(paths)
    for k in before:
        if before[k]["sha256"] != after[k]["sha256"]:
            raise SystemExit(f"STOP: input changed during the build: {k}")
    return after


# ------------------------------------------------------------------ release 0.1.0
def read_release(name: str) -> pd.DataFrame:
    p = RELEASE_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Release 0.1.0 file not found: {p}")
    return pd.read_csv(p, dtype={"fips": str})


def _to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _to_bool_str(s: pd.Series) -> pd.Series:
    return s.map(lambda v: "" if pd.isna(v) else str(v).strip().lower())


def compare_county(
    layer: str,
    snapshot: str,
    rec: pd.DataFrame,
    release: pd.DataFrame,
    exact_cols: Iterable[str] = (),
    float_cols: Iterable[str] = (),
    bool_cols: Iterable[str] = (),
) -> dict:
    """Identity check (SPEC 2.1 item 5): recomputed county layer == CSV of release 0.1.0.

    rec: index = county fips (the 3,109 CONUS counties), columns = layer fields and,
    if the layer has it, 'coverage_status'. Any difference writes a FAIL file and stops.
    """
    exact_cols, float_cols, bool_cols = list(exact_cols), list(float_cols), list(bool_cols)
    rel = release[release["fips"].notna()].set_index("fips")
    rel = rel[rel.index.str[:2].isin(CONUS_STATES_FIPS)]
    problems: list[str] = []

    only_rec = sorted(set(rec.index) - set(rel.index))
    only_rel = sorted(set(rel.index) - set(rec.index))
    if only_rec or only_rel:
        problems.append(f"fips sets differ: only recomputed={only_rec[:10]} only release={only_rel[:10]}")
    common = rec.index.intersection(rel.index)
    a, b = rec.loc[common], rel.loc[common]

    if "coverage_status" in rec.columns:
        bad = a["coverage_status"].astype(str) != b["coverage_status"].astype(str)
        if bad.any():
            problems.append(f"coverage_status differs in {int(bad.sum())} counties: {list(common[bad.values])[:10]}")

    for c in exact_cols + float_cols:
        x, y = _to_float(a[c]), _to_float(b[c])
        nan_diff = x.isna() != y.isna()
        both = ~(x.isna() | y.isna())
        if c in exact_cols:
            bad = nan_diff | (both & (x != y))
        else:
            bad = nan_diff | (both & ((x - y).abs() > FLOAT_TOL))
        if bad.any():
            ex = [(f, x.loc[f], y.loc[f]) for f in list(common[bad.values])[:8]]
            problems.append(f"{c}: {int(bad.sum())} counties differ (fips, recomputed, release): {ex}")

    for c in bool_cols:
        bad = _to_bool_str(a[c]) != _to_bool_str(b[c])
        if bad.any():
            problems.append(f"{c}: {int(bad.sum())} counties differ: {list(common[bad.values])[:10]}")

    if problems:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        fail = OUTPUT_DIR / f"adm1_identity_FAIL_{layer}_{snapshot}.txt"
        fail.write_text("\n".join(problems), encoding="utf-8")
        log.error("IDENTITY CHECK FAILED for %s. Details: %s", layer, fail)
        raise SystemExit(2)
    log.info("Identity with release 0.1.0 OK for %s: %d counties, columns %s",
             layer, len(common), exact_cols + float_cols + bool_cols)
    return {"status": "OK", "n_counties_compared": int(len(common)),
            "columns": exact_cols + float_cols + bool_cols,
            "release_file_dir": str(RELEASE_DIR)}


# ------------------------------------------------------------------ state frame / outputs
def build_state_frame(
    values: pd.DataFrame,
    value_cols: list[str],
    int_cols: Iterable[str] = (),
    bool_cols: Iterable[str] = (),
    nullable_cols: Iterable[str] = (),
) -> pd.DataFrame:
    """51 rows: unit_id, coverage_status, coverage_note, value columns.

    values is indexed by state FIPS (the 49 covered units). AK (02) and HI (15) get
    coverage_status = not_covered and empty values. coverage_note stays empty here:
    its text comes from [RES]7 and is filled in by [CODE-PUB]2.
    """
    su = state_units()
    missing = set(su.loc[su["covered"], "state_fips"]) - set(values.index)
    if missing:
        raise RuntimeError(f"No values for covered states: {sorted(missing)}")
    out = su.merge(values[value_cols], left_on="state_fips", right_index=True, how="left")
    out.loc[~out["covered"], value_cols] = np.nan
    nullable = set(nullable_cols)
    must = [c for c in value_cols if c not in nullable]
    if out.loc[out["covered"], must].isna().any().any():
        raise RuntimeError("Covered state with an empty value: " +
                           str(out.loc[out["covered"], must].isna().sum().to_dict()))
    for c in int_cols:
        out[c] = out[c].astype("Int64")
    for c in bool_cols:
        out[c] = pd.array(out[c].map(lambda v: pd.NA if pd.isna(v) else bool(v)), dtype="boolean")
    out["coverage_status"] = np.where(out["covered"], "covered", "not_covered")
    out["coverage_note"] = ""
    return out[["unit_id", "coverage_status", "coverage_note"] + value_cols]


def write_layer_csv(layer_name: str, df: pd.DataFrame, meta: dict, snapshot: str) -> Path:
    """layer_<name>_adm1_<date>.csv and layer_<name>_adm1_meta.json in data\\conus."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"layer_{layer_name}_adm1_{snapshot}.csv"
    df.to_csv(csv_path, index=False)
    log.info("CSV written: %s (%d rows)", csv_path, len(df))
    meta = dict(meta)
    meta.setdefault("snapshot_date", snapshot)
    meta["output_file"] = csv_path.name
    meta["output_sha256"] = sha256_file(csv_path)
    meta_path = OUTPUT_DIR / f"layer_{layer_name}_adm1_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    log.info("Meta written: %s", meta_path)
    return csv_path


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def check(name: str, expected, actual, tol: float = 0.0, note: str = "") -> dict:
    """One line of the build report: expected vs actual (ok=None when not comparable)."""
    try:
        ok = abs(float(actual) - float(expected)) <= tol
    except (TypeError, ValueError):
        ok = None
    return {"name": name, "expected": expected, "actual": actual, "ok": ok, "note": note}


def write_part(layer: str, snapshot: str, report: dict, recon: pd.DataFrame) -> None:
    """Parts for finish_adm1_report.py: numbers (json) and reconciliation rows (csv)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pj = OUTPUT_DIR / f"adm1_part_{layer}_{snapshot}.json"
    pj.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    pc = OUTPUT_DIR / f"adm1_recon_part_{layer}_{snapshot}.csv"
    recon.to_csv(pc, index=False)
    log.info("Report part: %s ; reconciliation part: %s", pj.name, pc.name)


# ------------------------------------------------------------------ reconciliation
@dataclass
class Cat:
    """One reconciliation category: records in the state value but not in the county sum (sign +1)
    or in the county sum but not in the state value (sign -1)."""
    name: str
    n: pd.Series        # number of records, index = state FIPS
    value: pd.Series    # MW / count / km of those records, index = state FIPS
    sign: int
    detail: dict = field(default_factory=dict)  # state FIPS -> short text


def reconcile(
    layer_id: str,
    field_name: str,
    unit: str,
    state_values: pd.Series,
    county_sums: pd.Series,
    cats: list[Cat],
) -> pd.DataFrame:
    """Rows of state_reconciliation: state value, county sum, difference, categories, residual.

    residual = (state - county_sum) - sum(sign * category value); it must be 0.
    """
    rows = []
    for s in sorted(state_values.index):
        sv = float(state_values.loc[s])
        cs = float(county_sums.get(s, 0.0))
        diff = sv - cs
        row = {"layer_id": layer_id, "unit_id": f"USA-1-{s}", "field": field_name, "unit": unit,
               "state_value": round(sv, 6), "county_sum": round(cs, 6), "difference": round(diff, 6)}
        explained = 0.0
        details = []
        for c in cats:
            v = float(c.value.get(s, 0.0))
            n = int(c.n.get(s, 0))
            row[f"{c.name}_n"] = n
            row[f"{c.name}_value"] = round(v, 6)
            explained += c.sign * v
            if c.detail.get(s):
                details.append(f"{c.name}: {c.detail[s]}")
        row["residual"] = round(diff - explained, 6)
        row["detail"] = " | ".join(details)
        rows.append(row)
    return pd.DataFrame(rows)


def county_sums_by_state(release: pd.DataFrame, col: str) -> pd.Series:
    """Sum of the published county CSV (release 0.1.0) per state; empty values count as 0."""
    r = release[release["fips"].notna()].copy()
    r = r[r["fips"].str[:2].isin(CONUS_STATES_FIPS)]
    r["_s"] = r["fips"].str[:2]
    return _to_float(r[col]).groupby(r["_s"]).sum()


def short_list(items: list[str], limit: int = 12) -> str:
    items = list(items)
    if len(items) <= limit:
        return "; ".join(items)
    return "; ".join(items[:limit]) + f"; ... (+{len(items) - limit})"
