r"""
adm1_common.py
==============
Helper module for the four ADM1 (state) builders: abf-layers 0.2.0 (SPEC_USA_states_v0_2_0 r5)
and 0.3.0 (SPEC_USA_AKHI_v0_3_0 r2: Alaska and Hawaii). NOT RUN DIRECTLY.

Put it in the same folder as gci_conus_common.py (scripts\conus\). It imports
gci_conus_common.py without changing it (SPEC r5 section 2.7).

Import order matters: this module sets the default county-shapefile path
(ABF_COUNTY_SHP) BEFORE gci_conus_common reads it, so every builder must
`import adm1_common` first.

--states all | contiguous   (default all)
    contiguous  the 48 states + DC and their 3,109 counties: reproduces the 0.2.0 build;
    all         the 50 states + DC and 3,144 counties (adds Alaska 02 with 30 counties and
                Hawaii 15 with 5). A source that does not cover a state keeps it not_covered.
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
    STORAGE_CRS,
    load_conus_counties,
    log,
    resolve_points_to_counties,
    safe_float,
)

REPO = OUTPUT_DIR.parent.parent  # ...\AI Buildup Frontier project
RELEASE_DIR = REPO / "data" / "abf-layers" / "v0.1.0"
UNITS_CSV = REPO / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
FLOAT_TOL = 1e-6  # SPEC 2.1 item 5: numbers to 1e-6, integers exactly

AKHI_FIPS = ("02", "15")
AKHI_USPS = ("AK", "HI")
N_COUNTIES = {"contiguous": 3109, "all": 3144}  # 3,109 + 30 (Alaska) + 5 (Hawaii)
PREV_ADM1_DATE = "20261107"  # the 0.2.0 build of the state layers


# ------------------------------------------------------------------ scope (--states)
@dataclass(frozen=True)
class Scope:
    mode: str
    fips: frozenset
    usps: frozenset

    @property
    def n_states(self) -> int:
        return len(self.fips)

    @property
    def n_counties(self) -> int:
        return N_COUNTIES[self.mode]


def make_scope(mode: str) -> Scope:
    if mode == "contiguous":
        return Scope(mode, frozenset(CONUS_STATES_FIPS), frozenset(CONUS_STATES_USPS))
    if mode == "all":
        return Scope(mode, frozenset(CONUS_STATES_FIPS) | frozenset(AKHI_FIPS),
                     frozenset(CONUS_STATES_USPS) | frozenset(AKHI_USPS))
    raise ValueError(f"--states must be all or contiguous, got {mode!r}")


CONTIGUOUS = make_scope("contiguous")


# ------------------------------------------------------------------ arguments
def base_parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "--snapshot-date",
        default=dt.date.today().strftime("%Y%m%d"),
        help="date tag of the output files, YYYYMMDD (default: today). "
        "Use the same value for all four builders and for finish_adm1_report.py.",
    )
    ap.add_argument(
        "--states", choices=["all", "contiguous"], default="all",
        help="all = 50 states + DC (3,144 counties), default; contiguous = 48 states + DC (3,109 counties), "
        "reproduces the 0.2.0 build.",
    )
    ap.add_argument(
        "--prev-date", default=PREV_ADM1_DATE,
        help="date tag of the previous (0.2.0) state files in data\\conus; the 49 contiguous state rows of this "
        "build must be identical to them (default: %(default)s).",
    )
    return ap


# ------------------------------------------------------------------ boundaries
def load_counties(scope: Scope):
    """Counties of the scope in JOIN_CRS (EPSG:5070): fips, NAME, NAMELSAD, STATEFP, geometry.

    contiguous = load_conus_counties() of gci_conus_common.py, unchanged (3,109).
    all        = the same file and the same columns with Alaska and Hawaii added (3,144).
    """
    if scope.mode == "contiguous":
        gdf = load_conus_counties()
    else:
        import geopandas as gpd

        if not BOUNDARY_SHP.exists():
            raise FileNotFoundError(f"County boundary file not found: {BOUNDARY_SHP}")
        gdf = gpd.read_file(BOUNDARY_SHP).rename(columns={"GEOID": "fips"})
        gdf = gdf[gdf["STATEFP"].isin(scope.fips)].copy().to_crs(JOIN_CRS)
        gdf = gdf[["fips", "NAME", "NAMELSAD", "STATEFP", "geometry"]].reset_index(drop=True)
        log.info("Counties loaded (%s): %d (expected %d)", scope.mode, len(gdf), scope.n_counties)
    if len(gdf) != scope.n_counties:
        raise SystemExit(f"STOP: {len(gdf)} counties loaded for --states {scope.mode}, expected {scope.n_counties}")
    return gdf


def usps_to_fips(scope: Optional[Scope] = None) -> dict[str, str]:
    """Postal code -> state FIPS, from STUSPS/STATEFP of the county file (SPEC 2.1 item 3), for the scope."""
    import pyogrio

    scope = scope or CONTIGUOUS
    df = pyogrio.read_dataframe(BOUNDARY_SHP, read_geometry=False, columns=["STATEFP", "STUSPS"])
    pairs = df.drop_duplicates()
    mapping = {r.STUSPS: r.STATEFP for r in pairs.itertuples() if r.STATEFP in scope.fips}
    if len(mapping) != scope.n_states or set(mapping) != set(scope.usps):
        raise RuntimeError(f"STUSPS->STATEFP map is not the expected {scope.n_states} units: {len(mapping)}")
    return mapping


def state_units(covered_fips: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """The 51 USA ADM1 rows from units.csv of abf-boundaries v0.2.0.

    covered_fips = the state FIPS this source covers (default: the 49 contiguous units).
    """
    cov = set(CONUS_STATES_FIPS if covered_fips is None else covered_fips)
    u = pd.read_csv(UNITS_CSV, dtype=str)
    s = u[u["unit_id"].str.startswith("USA-1-")][["unit_id"]].copy()
    s["state_fips"] = s["unit_id"].str[-2:]
    s["covered"] = s["state_fips"].isin(cov)
    if len(s) != 51 or int(s["covered"].sum()) != len(cov):
        raise RuntimeError(f"units.csv: expected 51 USA-1-* rows / {len(cov)} covered, "
                           f"got {len(s)} / {int(s['covered'].sum())}")
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


def _stop_with(problems: list[str], fail_name: str, what: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fail = OUTPUT_DIR / fail_name
    fail.write_text("\n".join(problems), encoding="utf-8")
    log.error("%s. Details: %s", what, fail)
    raise SystemExit(2)


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

    rec: index = county fips, columns = layer fields and, if the layer has it, 'coverage_status'.
    Only the 3,109 contiguous counties are compared (release 0.1.0 has no others), also in a
    --states all run; Alaska and Hawaii counties are new and have nothing to be compared with.
    Any difference writes a FAIL file and stops.
    """
    exact_cols, float_cols, bool_cols = list(exact_cols), list(float_cols), list(bool_cols)
    rec = rec[rec.index.str[:2].isin(CONUS_STATES_FIPS)]
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
        _stop_with(problems, f"adm1_identity_FAIL_{layer}_{snapshot}.txt", f"IDENTITY CHECK FAILED for {layer}")
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
    covered_fips: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """51 rows: unit_id, coverage_status, coverage_note, value columns.

    values is indexed by state FIPS (the covered units of this source). The other units get
    coverage_status = not_covered and empty values. coverage_note stays empty here: its text
    comes from [RES]7 and is filled in by [CODE-PUB]2.
    """
    su = state_units(covered_fips)
    missing = set(su.loc[su["covered"], "state_fips"]) - set(values.index)
    if missing:
        raise RuntimeError(f"No values for covered states: {sorted(missing)}")
    out = su.merge(values[value_cols], left_on="state_fips", right_index=True, how="left")
    for c in bool_cols:  # a bool column cannot take NaN (pandas FutureWarning): go through object first
        out[c] = out[c].astype(object)
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
    """layer_<name>_adm1_<date>.csv and layer_<name>_adm1_<date>_meta.json in data\\conus."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"layer_{layer_name}_adm1_{snapshot}.csv"
    df.to_csv(csv_path, index=False)
    log.info("CSV written: %s (%d rows)", csv_path, len(df))
    meta = dict(meta)
    meta.setdefault("snapshot_date", snapshot)
    meta["output_file"] = csv_path.name
    meta["output_sha256"] = sha256_file(csv_path)
    # dated name: the _meta.json of the 0.2.0 build (layer_<name>_adm1_meta.json, committed) is not overwritten
    meta_path = OUTPUT_DIR / f"layer_{layer_name}_adm1_{snapshot}_meta.json"
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


def stop_if_failed(checks: list[dict], layer: str) -> None:
    """After everything is written: a check that did not match stops the run with exit code 3
    (the outputs and the part files are already on disk, so the difference can be examined)."""
    bad = [c for c in checks if c["ok"] is False]
    if bad:
        for c in bad:
            log.error("CHECK FAILED [%s]: %s - expected %s, got %s", layer, c["name"], c["expected"], c["actual"])
        log.error("STOP: %d check(s) did not match for %s. Do not commit; send the console output.", len(bad), layer)
        raise SystemExit(3)


# ------------------------------------------------------------------ 49 contiguous rows against the 0.2.0 build
def compare_state_prev(
    layer: str,
    snapshot: str,
    out: pd.DataFrame,
    prev_date: str,
    exact_cols: Iterable[str] = (),
    float_cols: Iterable[str] = (),
    bool_cols: Iterable[str] = (),
) -> dict:
    """The 49 contiguous state rows of this build must equal layer_<layer>_adm1_<prev_date>.csv
    (the 0.2.0 build) in every column: integers exactly, numbers to 1e-6. Any difference stops."""
    exact_cols, float_cols, bool_cols = list(exact_cols), list(float_cols), list(bool_cols)
    p = OUTPUT_DIR / f"layer_{layer}_adm1_{prev_date}.csv"
    if not p.exists():
        raise SystemExit(f"STOP: the 0.2.0 state file is needed for the identity check, not found: {p}")
    prev = pd.read_csv(p, dtype={"unit_id": str}, keep_default_na=False, na_values=[""]).set_index("unit_id")
    new = out.set_index("unit_id")
    conus_ids = [f"USA-1-{f}" for f in sorted(CONUS_STATES_FIPS)]
    problems: list[str] = []
    if set(prev.index) != set(new.index):
        problems.append(f"unit_id sets differ: only prev {sorted(set(prev.index) - set(new.index))[:5]}, "
                        f"only new {sorted(set(new.index) - set(prev.index))[:5]}")
    ids = [i for i in conus_ids if i in prev.index and i in new.index]
    a, b = new.loc[ids], prev.loc[ids]
    if list(prev.columns) != list(new.columns):
        problems.append(f"columns differ: prev {list(prev.columns)} new {list(new.columns)}")
    for c in [c for c in prev.columns if c in new.columns]:
        if c in exact_cols + float_cols:
            x, y = _to_float(a[c]), _to_float(b[c])
            nan_diff = x.isna() != y.isna()
            both = ~(x.isna() | y.isna())
            bad = nan_diff | (both & ((x != y) if c in exact_cols else ((x - y).abs() > FLOAT_TOL)))
        elif c in bool_cols:
            bad = _to_bool_str(a[c]) != _to_bool_str(b[c])
        else:
            bad = a[c].fillna("").astype(str) != b[c].fillna("").astype(str)
        if bad.any():
            ex = [(i, a.loc[i, c], b.loc[i, c]) for i in list(a.index[bad.values])[:6]]
            problems.append(f"{c}: {int(bad.sum())} states differ (unit, new, 0.2.0): {ex}")
    if problems:
        _stop_with(problems, f"adm1_identity_state_FAIL_{layer}_{snapshot}.txt",
                   f"STATE IDENTITY WITH THE 0.2.0 BUILD FAILED for {layer}")
    log.info("Identity of the %d contiguous state rows with %s OK for %s", len(ids), p.name, layer)
    return {"status": "OK", "file": p.name, "n_states_compared": len(ids), "columns": list(prev.columns)}


def additivity_checks(out: pd.DataFrame, prev_date: str, layer: str, cols: list[str], tol: float = 1e-6) -> list[dict]:
    """Total over the covered states of this build = total of the 49 states of the 0.2.0 build
    + Alaska + Hawaii of this build (a sum column per check)."""
    p = OUTPUT_DIR / f"layer_{layer}_adm1_{prev_date}.csv"
    prev = pd.read_csv(p, dtype={"unit_id": str})
    prev49 = prev[prev["coverage_status"] == "covered"]
    new = out[out["coverage_status"] == "covered"]
    akhi = new[new["unit_id"].isin([f"USA-1-{f}" for f in AKHI_FIPS])]
    res = []
    for c in cols:
        total_new = float(_to_float(new[c]).sum())
        expect = float(_to_float(prev49[c]).sum()) + float(_to_float(akhi[c]).sum())
        res.append(check(f"{c}: total of the covered states = 49 states of 0.2.0 + AK + HI",
                         round(expect, 6), round(total_new, 6), tol=tol,
                         note=f"0.2.0: {float(_to_float(prev49[c]).sum()):,.3f}; AK+HI: {float(_to_float(akhi[c]).sum()):,.3f}"))
    return res


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


def combined_reference(release: pd.DataFrame, rec: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Per-county reference values for the county sums of state_reconciliation.

    The 3,109 contiguous counties come from the published CSV of release 0.1.0 (as in 0.2.0); the
    Alaska and Hawaii counties, which that CSV does not have, come from this run (rec, index = fips).
    Returns a table with a 'fips' column and the requested columns.
    """
    rel = release[release["fips"].notna()][["fips"] + cols]
    rel = rel[rel["fips"].str[:2].isin(CONUS_STATES_FIPS)]
    extra = rec[rec.index.str[:2].isin(AKHI_FIPS)][cols].rename_axis("fips").reset_index()
    return pd.concat([rel, extra], ignore_index=True)


def county_sums_by_state(release: pd.DataFrame, col: str, states: Optional[Iterable[str]] = None) -> pd.Series:
    """Sum of a per-county table per state; empty values count as 0 (default: the contiguous states)."""
    st = set(CONUS_STATES_FIPS if states is None else states)
    r = release[release["fips"].notna()].copy()
    r = r[r["fips"].str[:2].isin(st)]
    r["_s"] = r["fips"].str[:2]
    return _to_float(r[col]).groupby(r["_s"]).sum()


def short_list(items: list[str], limit: int = 12) -> str:
    items = list(items)
    if len(items) <= limit:
        return "; ".join(items)
    return "; ".join(items[:limit]) + f"; ... (+{len(items) - limit})"


# ------------------------------------------------------------------ county tables for the release (legacy format)
def read_legacy_meta(name: str) -> dict:
    """Meta of the previous county table (the one the layer yaml points to), as the starting point."""
    p = OUTPUT_DIR / name
    if not p.exists():
        log.warning("Previous county meta not found, starting empty: %s", p)
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_county_table(legacy_name: str, df: pd.DataFrame, meta: dict, snapshot: str) -> Path:
    """layer_<legacy_name>_<date>.csv + layer_<legacy_name>_<date>_meta.json in data\\conus: the county
    table in the format and with the column names of the tables of 0.1.0 / 0.2.0 (the layer yaml of
    abf-layers reads exactly this; only its path changes)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"layer_{legacy_name}_{snapshot}.csv"
    df.to_csv(csv_path, index=False)
    log.info("County table written: %s (%d rows)", csv_path, len(df))
    meta = dict(meta)
    meta["snapshot_date"] = snapshot
    meta["output_file"] = csv_path.name
    meta["output_sha256"] = sha256_file(csv_path)
    meta_path = OUTPUT_DIR / f"layer_{legacy_name}_{snapshot}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    log.info("County table meta written: %s", meta_path)
    return csv_path


def compare_text_to_legacy(new_csv: Path, legacy_csv: Path) -> dict:
    """Report only (never stops): are the rows of the legacy county table reproduced text for text?
    Values are already proved identical to release 0.1.0; this also shows formatting (number
    spelling, names) in the new file. Compared on the fips of the legacy table."""
    if not legacy_csv.exists():
        return {"status": "legacy file not found", "file": legacy_csv.name}
    a = pd.read_csv(new_csv, dtype=str, keep_default_na=False).set_index("fips")
    b = pd.read_csv(legacy_csv, dtype=str, keep_default_na=False).set_index("fips")
    common = b.index.intersection(a.index)
    cols = [c for c in b.columns if c in a.columns]
    diff_rows = int((a.loc[common, cols] != b.loc[common, cols]).any(axis=1).sum())
    return {"status": "identical" if not diff_rows and list(a.columns[:len(b.columns)]) == list(b.columns)
            and len(common) == len(b) else "differs",
            "file": legacy_csv.name, "rows_in_legacy": int(len(b)), "rows_compared": int(len(common)),
            "rows_with_text_difference": diff_rows,
            "columns_equal": list(a.columns[:len(b.columns)]) == list(b.columns)}
