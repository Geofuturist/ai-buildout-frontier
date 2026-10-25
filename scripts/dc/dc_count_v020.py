r"""abf-dc 0.2.0: data step (SPEC_DC_world_v0_2_0 r1, section 2).

Reads only published files of earlier releases, no network:
  dc_atlas_points.csv  from abf-dc 0.1.0         (SHA-256 pinned)
  units.csv            from abf-boundaries 0.2.0 (SHA-256 pinned)
  operator_type_groups.csv (data/dc/rules, in git; SPEC r2 section 8: 20 Atlas operator types -> 7 display groups; its numbers are checked
                       against the points, its SHA-256 goes into sources_manifest.json)
Writes `dc_atlas_count_places.csv` (Atlas records with a point, by place, with the operator-type groups), `dc_atlas_count_usa_adm2.csv`
(Atlas records of the US by the county the record names), `county_records.csv`, `operator_type_groups.csv` (a copy with LF line ends),
`sources_manifest.json`, `build_report.md`.

The county rule is the rule of step 4 of the place chain (SPEC 0.1.0 section 2.3): text normalisation `dc_lib.norm` and the
type-word pattern `dc_place.ADM2_TYPE_WORD` are imported, not copied; the link check (section 2.3 item 5) proves they agree.
A run is reproducible: same inputs and same --checked-at give byte-identical CSV files (P5).

Windows cmd, from the repo root:

    python scripts\dc\dc_count_v020.py --points "data\abf-dc\v0.1.0\dc_atlas_points.csv" --units "data\abf-boundaries\v0.2.0\units.csv" --out-dir "D:\GISData\AI\DC\out\abf-dc-v0.2.0" --checked-at 2026-10-24T12:00:00Z

Optional, for the report of section 2.3 item 7 (points that lie in another county than the record names):
    --analysis-adm2 <analysis_usa_adm2.parquet> --sources-manifest <sources_manifest.json of abf-dc 0.1.0> (may be repeated)
    --groups <operator_type_groups.csv>   (default: data\\dc\\rules\\operator_type_groups.csv of the repository)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc_count import CLASS_COLS, STATUS_COLS, VALUE_COLS  # noqa: E402
from dc_lib import BuildStop, norm  # noqa: E402
from dc_place import ADM2_TYPE_WORD  # noqa: E402

VERSION = "abf-dc 0.2.0 data step r1"
CHECKED_BY = "script:dc_count_v020"
PINNED = {
    "points": ("dc_atlas_points.csv of abf-dc 0.1.0", "b4d4aabdbed7d76cc13081bcabe1db6426fe9af57b2781bc3e5f40c93bed1df5"),
    "units": ("units.csv of abf-boundaries 0.2.0", "126b8017034c2c72a181a47f2aa8d454f0dcadd3a856d9d0fc9ed785f3093e4d"),
}
CT_UNIT = "USA-1-09"
GROUPS = ["colocation", "telecom", "developer_investor", "cloud", "enterprise_it", "ai_compute", "other"]   # order of the legend (RES_texts_DC_v0_2_0 9.1)
TYPE_COLS = [f"n_type_{g}" for g in GROUPS]
DEFAULT_GROUPS = Path(__file__).resolve().parents[2] / "data" / "dc" / "rules" / "operator_type_groups.csv"
PLACE_SHARED = ["lon", "lat", "place_name", "iso3_source", "iso3_frame", "control_iso3"]
ASSIGNMENTS = ["no_state", "connecticut", "no_county_field", "ambiguous_name", "not_matched", "matched"]

# Expected numbers, SPEC section 2.4: the inputs are pinned by hash, so the numbers must match exactly (a stop).
EXPECT = {
    "places.rows": 2303, "places.total": 6087, "places.single": 1424, "places.mid_2_9": 770, "places.big_10_plus": 109,
    "places.max": 80, "places.max_ref": "geonames:1796236",
    "us.total": 4038, "us.no_state": 1, "us.connecticut": 21, "us.no_county_field": 32, "us.ambiguous_name": 70, "us.not_matched": 0,
    "us.matched": 3914, "us.ambiguous_groups": [46, 14, 9, 1],
    "county.units": 3144, "county.ct_units": 9, "county.not_covered": 17, "county.with_records": 812, "county.sum": 3914,
    "county.max": 179, "county.max_unit": "USA-2-51107", "link.county_precision": 1583,
    # SPEC r2 section 8 item 4 (order of GROUPS)
    "types.points_with_point": [2774, 1089, 671, 562, 386, 138, 467], "types.single_places": [474, 233, 253, 115, 124, 39, 186],
    "types.places_2plus": 879, "types.places_mixed": 571, "types.records": 9865, "types.n_operator_types": 20,
}
# SPEC section 3 item 5: classes of the display breaks [1, 3, 10, 30, 100] (report only, not a stop)
EXPECT_DISPLAY_CLASSES = [482, 240, 71, 16, 3]

# Provisional texts of `coverage_note` (English, G7). The final wording is [RES]7's; these are replaced there, the numbers stay.
# `coverage_note` texts of RES_texts_DC_v0_2_0 r2 section 2 (the number {n} is filled in here)
NOTE_CT = ("Not covered: the Atlas gives Connecticut's eight historical counties, and the boundary frame has the nine "
           "planning regions that replaced them as county equivalents in 2022. No Atlas record of the state "
           "({n} in all) is counted under a unit.")
NOTE_PAIR = ("Not covered: a county and an independent city of this state share this name, and the Atlas records "
             "that give it do not say which of the two they mean ({n} in all). Neither unit is counted.")


class Problems:
    """Collects failed expectations so that one stop lists all of them."""

    def __init__(self):
        self.items: list[str] = []

    def expect(self, label: str, got, want):
        if got != want:
            self.items.append(f"{label}: got {got}, expected {want}")

    def check(self, ok: bool, msg: str):
        if not ok:
            self.items.append(msg)

    def raise_if_any(self):
        if self.items:
            raise BuildStop("; ".join(self.items))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_pinned(path: str, key: str):
    """Read a CSV whose SHA-256 is pinned. A git checkout on Windows may turn LF into CRLF; if the hash of the file with
    CRLF -> LF equals the pinned one, the published bytes are restored and read (the report says so)."""
    label, want = PINNED[key]
    raw = Path(path).read_bytes()
    how = "as is"
    got = sha256_bytes(raw)
    if got != want:
        lf = raw.replace(b"\r\n", b"\n")
        if sha256_bytes(lf) == want:
            raw, got, how = lf, want, "CRLF replaced by LF (git line-ending conversion); SHA-256 of the restored bytes equals the pinned one"
        else:
            raise BuildStop(f"{label}: SHA-256 {got} (also tried with CRLF -> LF) is not the pinned {want}; file {path}")
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    return df, dict(file=Path(path).name, what=label, bytes=len(raw), sha256=got, read=how)


def read_groups(path: str):
    """operator_type_groups.csv (SPEC r2 section 8 item 2). Read with CRLF -> LF (git on Windows); returns (table, info, LF bytes)."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    if list(df.columns) != ["operator_type", "type_group", "n_records"]:
        raise BuildStop(f"operator_type_groups.csv: columns {list(df.columns)}, expected operator_type, type_group, n_records")
    if df["operator_type"].duplicated().any():
        raise BuildStop("operator_type_groups.csv: an operator_type is listed twice")
    bad = sorted(set(df["type_group"]) - set(GROUPS))
    if bad:
        raise BuildStop(f"operator_type_groups.csv: unknown type_group {bad}; allowed {GROUPS}")
    missing = sorted(set(GROUPS) - set(df["type_group"]))
    if missing:
        raise BuildStop(f"operator_type_groups.csv: no operator type in the groups {missing}")
    return df, dict(file=Path(path).name, what="operator_type_groups.csv (data/dc/rules)", bytes=len(raw), sha256=sha256_bytes(raw),
                    read="CRLF replaced by LF"), raw


def add_groups(pts: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    """SPEC r2 section 8 item 2 stops: every operator type of the points is in the table; n_records of each row is the number of
    points of that type; the sum is the number of points. Returns the points with the column type_group."""
    types = pts["operator_type"]
    unknown = sorted(set(types) - set(groups["operator_type"]))
    if unknown:
        raise BuildStop(f"operator_type of the points that is not in operator_type_groups.csv: {unknown}")
    have = types.value_counts()
    bad = [f"{r.operator_type}: table {r.n_records}, points {int(have.get(r.operator_type, 0))}" for r in groups.itertuples(index=False)
           if int(r.n_records) != int(have.get(r.operator_type, 0))]
    if bad:
        raise BuildStop("n_records of operator_type_groups.csv differs from the points: " + "; ".join(bad))
    if int(pd.to_numeric(groups["n_records"]).sum()) != len(pts):
        raise BuildStop(f"sum of n_records of operator_type_groups.csv {int(pd.to_numeric(groups['n_records']).sum())} differs from the number of points {len(pts)}")
    out = pts.copy()
    out["type_group"] = types.map(dict(zip(groups["operator_type"], groups["type_group"])))
    return out


# ------------------------------------------------------------------------------------------------ counts

def tally(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """n_records, status and class columns per value of `key` (same columns and class codes as dc_atlas_count_adm0)."""
    base = df.groupby(key).size().rename("n_records").to_frame()
    for st, col in STATUS_COLS.items():
        base[col] = (df["status_raw"] == st).groupby(df[key]).sum()
    for cl, col in CLASS_COLS.items():
        base[col] = (df["power_class"] == cl).groupby(df[key]).sum()
    base = base.astype(int)
    st_sum = base[list(STATUS_COLS.values())].sum(axis=1)
    cl_sum = base[list(CLASS_COLS.values())].sum(axis=1)
    bad = base.index[(st_sum != base["n_records"]) | (cl_sum != base["n_records"])]
    if len(bad):
        raise BuildStop(f"sum by status or by class differs from n_records for {len(bad)} rows of {key}, first: {list(bad[:5])}")
    return base[VALUE_COLS]


def ws_id(s: str) -> str:
    return "PLC-" + s.replace(":", "-")


def build_places(pts: pd.DataFrame, checked_at: str) -> pd.DataFrame:
    """`pts` has the column type_group (add_groups)."""
    city = pts[pts["coord_precision"] == "city"]
    if (city["place_ref"] == "").any():
        raise BuildStop(f"{int((city['place_ref'] == '').sum())} records with coord_precision city have no place_ref, first: "
                        f"{list(city.loc[city['place_ref'] == '', 'record_id'][:5])}")
    other = pts[pts["coord_precision"] != "city"]
    if (other["place_ref"] != "").any():
        raise BuildStop(f"{int((other['place_ref'] != '').sum())} records with coord_precision other than city have a place_ref, first: "
                        f"{list(other.loc[other['place_ref'] != '', 'record_id'][:5])}")
    g = city.groupby("place_ref", sort=True)
    for col in PLACE_SHARED:
        nun = g[col].nunique()
        bad = nun[nun > 1]
        if len(bad):
            raise BuildStop(f"records of one place_ref differ in {col}: {len(bad)} places, first: {list(bad.index[:5])}")
    first = g[PLACE_SHARED].first()
    t = tally(city, "place_ref")
    out = first.join(t)
    out.index.name = "place_ref"
    out = out.reset_index()
    out["record_id"] = out["place_ref"].map(ws_id)
    if out["record_id"].duplicated().any():
        raise BuildStop("record_id of places is not unique")
    out["coord_precision"] = "city"
    out["ref"] = "abf-dc 0.1.0, dc_atlas_points, records with place_ref " + out["place_ref"]
    out["checked_at"], out["checked_by"] = checked_at, CHECKED_BY
    single = g["power_class"].first().where(t["n_records"].values == 1, "").reindex(out["place_ref"]).values
    out["power_class"] = single
    tg = g["type_group"].first().where(t["n_records"].values == 1, "").reindex(out["place_ref"]).values
    out["type_group"] = tg
    for grp, col in zip(GROUPS, TYPE_COLS):
        out[col] = (city["type_group"] == grp).groupby(city["place_ref"]).sum().reindex(out["place_ref"]).astype(int).values
    if (out[TYPE_COLS].sum(axis=1) != out["n_records"]).any():
        raise BuildStop("sum of n_type_* differs from n_records in " + str(int((out[TYPE_COLS].sum(axis=1) != out["n_records"]).sum())) + " places")
    if ((out["n_records"] == 1) & (out["type_group"] == "")).any() or ((out["n_records"] >= 2) & (out["type_group"] != "")).any():
        raise BuildStop("type_group is empty for a place with one record or filled for a place with several")
    cols = ["record_id", "place_ref", "place_name", "lon", "lat", "coord_precision", "iso3_source", "iso3_frame", "control_iso3",
            "ref", "checked_at", "checked_by", *VALUE_COLS, "power_class", "type_group", *TYPE_COLS]
    out = out[cols].sort_values("record_id", kind="stable").reset_index(drop=True)
    if int(out["n_records"].sum()) != len(city):
        raise BuildStop(f"sum of n_records over places is {int(out['n_records'].sum())}, records with a point {len(city)}")
    return out


def build_counties(pts: pd.DataFrame, units: pd.DataFrame):
    """-> (county_records, county layer, notes) following SPEC section 2.3."""
    adm1 = units[(units["iso3"] == "USA") & (units["level"] == "ADM1")]
    adm2 = units[(units["iso3"] == "USA") & (units["level"] == "ADM2")]
    state_unit = {norm(r.name): r.unit_id for r in adm1.itertuples(index=False)}
    if state_unit.get("connecticut") != CT_UNIT:
        raise BuildStop(f"Connecticut is {state_unit.get('connecticut')} in units.csv, expected {CT_UNIT}")
    idx: dict[str, dict[str, list[str]]] = {}
    for r in adm2.itertuples(index=False):
        idx.setdefault(r.parent_id, {}).setdefault(norm(r.name), []).append(r.unit_id)

    us = pts[pts["iso3_source"] == "USA"].sort_values("record_id", kind="stable")
    rows = []
    for r in us.itertuples(index=False):
        a1, a2 = r.adm1_raw, r.adm2_raw
        su = state_unit.get(norm(a1)) if a1.strip() else None
        cand: list[str] = []
        if su is None:
            how = "no_state"
        elif su == CT_UNIT:
            how = "connecticut"
        elif not a2.strip():
            how = "no_county_field"
        else:
            by_name = idx.get(su, {})
            cand = by_name.get(norm(a2), [])
            if not cand:
                stripped = ADM2_TYPE_WORD.sub("", a2)
                if stripped != a2:
                    cand = by_name.get(norm(stripped), [])
            how = "matched" if len(cand) == 1 else "ambiguous_name" if len(cand) > 1 else "not_matched"
        rows.append(dict(record_id=r.record_id, unit_id=cand[0] if how == "matched" else "", assignment=how,
                         candidates=";".join(sorted(cand)) if how == "ambiguous_name" else ""))
    cr = pd.DataFrame(rows, columns=["record_id", "unit_id", "assignment", "candidates"])
    if cr["record_id"].duplicated().any():
        raise BuildStop("record_id of US records is not unique")

    # frame, coverage
    frame = pd.DataFrame({"unit_id": sorted(adm2["unit_id"])}).merge(adm2[["unit_id", "name", "parent_id"]], on="unit_id", how="left")
    frame["fips"] = frame["unit_id"].str.split("-").str[2]
    if not frame["fips"].str.fullmatch(r"\d{5}").all():
        raise BuildStop("a unit_id of the US ADM2 frame has no 5-digit code")
    ct_units = set(frame.loc[frame["parent_id"] == CT_UNIT, "unit_id"])
    amb = cr[cr["assignment"] == "ambiguous_name"]
    amb_units: Counter = Counter()
    for c in amb["candidates"]:
        for u in c.split(";"):
            amb_units[u] += 1
    not_covered = ct_units | set(amb_units)
    n_ct = int((cr["assignment"] == "connecticut").sum())
    notes = {}
    for u in sorted(ct_units):
        notes[u] = NOTE_CT.format(n=n_ct)
    for u, n in sorted(amb_units.items()):
        notes[u] = (notes[u] + " " if u in notes else "") + NOTE_PAIR.format(n=n)

    us_c = us.assign(cunit=us["record_id"].map(cr.set_index("record_id")["unit_id"]))
    t = tally(us_c[us_c["cunit"] != ""], "cunit")
    layer = frame[["unit_id", "fips", "name"]].copy()
    layer["coverage_status"] = ["not_covered" if u in not_covered else "covered" for u in layer["unit_id"]]
    layer["coverage_note"] = [notes.get(u, "") for u in layer["unit_id"]]
    vals = t.reindex(layer["unit_id"]).fillna(0).astype(int).reset_index(drop=True)
    vals.index = layer.index
    for c in VALUE_COLS:
        layer[c] = vals[c].astype(object)
    nc = layer["coverage_status"] == "not_covered"
    layer.loc[nc, VALUE_COLS] = ""
    layer = layer[["unit_id", "fips", "name", "coverage_status", "coverage_note", *VALUE_COLS]]
    return cr[["record_id", "unit_id", "assignment", "candidates"]], layer, dict(ct_units=ct_units, amb_units=amb_units, n_ct=n_ct)


# ------------------------------------------------------------------------------------------------ report pieces

def find_sha(obj, needle: str):
    """First `sha256` of a manifest entry whose key or file name contains `needle` (the manifest layout is not fixed)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and needle in str(k) and "sha256" in v:
                return v["sha256"]
            hit = find_sha(v, needle)
            if hit:
                return hit
        if needle in str(obj.get("path", obj.get("file", ""))) and "sha256" in obj:
            return obj["sha256"]
    elif isinstance(obj, list):
        for v in obj:
            hit = find_sha(v, needle)
            if hit:
                return hit
    return None


def point_vs_named_county(pts: pd.DataFrame, cr: pd.DataFrame, parquet: Path, manifests: list[Path], lines: list[str]) -> dict:
    """SPEC section 2.3 item 7. Same predicate as Frame.county_of: point `within` the polygon of analysis_usa_adm2."""
    import geopandas as gpd
    from shapely import points as shp_points

    info = {}
    if not parquet.is_file():
        raise BuildStop(f"--analysis-adm2 {parquet}: file not found")
    raw = parquet.read_bytes()
    got = sha256_bytes(raw)
    want = None
    for m in manifests:
        if not Path(m).is_file():
            raise BuildStop(f"--sources-manifest {m}: file not found")
        want = find_sha(json.loads(Path(m).read_text(encoding="utf-8")), "analysis_usa_adm2")
        if want:
            break
    if want and want != got:
        raise BuildStop(f"{parquet.name}: SHA-256 {got} differs from the sources_manifest.json of abf-dc 0.1.0 ({want})")
    info["parquet_sha256"], info["hash_checked_against_manifest"] = got, bool(want)
    us2 = gpd.read_parquet(parquet)[["unit_id", "geometry"]].reset_index(drop=True)
    j = pts[(pts["iso3_source"] == "USA") & (pts["coord_precision"] == "city")].merge(
        cr[["record_id", "unit_id", "assignment"]].rename(columns={"unit_id": "named_unit"}), on="record_id")
    named = j[j["assignment"] == "matched"].reset_index(drop=True)
    p = shp_points(named["lon"].astype(float).values, named["lat"].astype(float).values)
    q_in, q_tree = us2.sindex.query(p, predicate="within")
    first = pd.Series(q_tree).groupby(q_in).min()           # first hit, as county_of takes hits[0]
    at = pd.Series([None] * len(named), dtype=object)
    at.loc[first.index] = us2["unit_id"].values[first.values]
    same = int((at == named["named_unit"]).sum())
    outside = int(at.isna().sum())
    other = len(named) - same - outside
    info.update(records_with_point_and_named_county=len(named), same_county=same, other_county=other, outside_all_counties=outside,
                us_city_points_without_named_county=int(len(j) - len(named)))
    lines += ["", "## US records with a point: point against the county the record names (SPEC 2.3 item 7)", "",
              f"- records of the US with a point (`city`) and a named county (`matched`): {len(named)}",
              f"- point lies in the named county: {same}",
              f"- **point lies in another county: {other}**",
              f"- point lies in no county of `analysis_usa_adm2`: {outside}",
              f"- records of the US with a point and no named county (other categories): {info['us_city_points_without_named_county']}",
              f"- `analysis_usa_adm2.parquet` SHA-256 {got} ({'equals the entry of the sources manifest' if want else 'no entry found in the given manifests: not compared'})"]
    return info


# ------------------------------------------------------------------------------------------------ main

def write_csv(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--points", required=True, help="dc_atlas_points.csv of abf-dc 0.1.0")
    ap.add_argument("--units", required=True, help="units.csv of abf-boundaries 0.2.0")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--checked-at", required=True, help="checked_at of the new rows, YYYY-MM-DDTHH:MM:SSZ (fixed so that a rerun gives the same bytes)")
    ap.add_argument("--groups", default=str(DEFAULT_GROUPS), help="operator_type_groups.csv (SPEC r2 section 8), default: data/dc/rules in the repository")
    ap.add_argument("--analysis-adm2", default=None, help="analysis_usa_adm2.parquet, for the report of SPEC 2.3 item 7")
    ap.add_argument("--sources-manifest", action="append", default=[], help="sources_manifest.json of abf-dc 0.1.0 (hash of the parquet)")
    a = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", a.checked_at):
        raise SystemExit("STOP: --checked-at must look like 2026-10-24T12:00:00Z")
    try:
        run(a)
    except BuildStop as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)


def run(a):
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pts, in_pts = read_pinned(a.points, "points")
    units, in_units = read_pinned(a.units, "units")
    need = {"record_id", "unit_id", "lon", "lat", "coord_precision", "place_name", "place_ref", "status_raw", "power_class", "adm1_raw",
            "adm2_raw", "iso3_source", "iso3_frame", "control_iso3"}
    need |= {"operator_type"}
    miss = need - set(pts.columns)
    if miss:
        raise BuildStop(f"dc_atlas_points.csv has no columns {sorted(miss)}")
    if pts["record_id"].duplicated().any():
        raise BuildStop("record_id of dc_atlas_points is not unique")

    if not Path(a.groups).exists():
        raise BuildStop(f"operator_type_groups.csv not found: {a.groups} (data/dc/rules/ in the repository; --groups)")
    groups, in_groups, groups_bytes = read_groups(a.groups)
    pts = add_groups(pts, groups)

    pr = Problems()
    lines = ["# abf-dc 0.2.0 data step: build report", "", f"{VERSION}; checked_at {a.checked_at}; checked_by {CHECKED_BY}.", "",
             "## Inputs", ""]
    for i in (in_pts, in_units, in_groups):
        lines.append(f"- {i['what']}: `{i['file']}`, {i['bytes']} bytes, SHA-256 `{i['sha256']}` (read: {i['read']})")

    # ---- places
    places = build_places(pts, a.checked_at)
    n = places["n_records"]
    pr.expect("places.rows", len(places), EXPECT["places.rows"])
    pr.expect("places.total", int(n.sum()), EXPECT["places.total"])
    pr.expect("places.single", int((n == 1).sum()), EXPECT["places.single"])
    pr.expect("places.mid_2_9", int(((n >= 2) & (n <= 9)).sum()), EXPECT["places.mid_2_9"])
    pr.expect("places.big_10_plus", int((n >= 10).sum()), EXPECT["places.big_10_plus"])
    top = places.loc[n.idxmax()]
    pr.expect("places.max", int(top["n_records"]), EXPECT["places.max"])
    pr.expect("places.max_ref", top["place_ref"], EXPECT["places.max_ref"])
    pr.check(int(((n == 1) & (places["power_class"] == "")).sum()) == int(((n == 1) & (places["n_class_unknown"] == 1)).sum()),
             "power_class of single-record places: empty class does not match n_class_unknown")
    pr.check(bool((places.loc[n >= 2, "power_class"] == "").all()), "a place with two or more records has a power_class")
    city = pts[pts["coord_precision"] == "city"]
    pr.expect("types.points_with_point", [int((city["type_group"] == g).sum()) for g in GROUPS], EXPECT["types.points_with_point"])
    pr.expect("types.single_places", [int(((places["type_group"] == g)).sum()) for g in GROUPS], EXPECT["types.single_places"])
    pr.expect("types.places_2plus", int((n >= 2).sum()), EXPECT["types.places_2plus"])
    mixed = city.groupby("place_ref")["type_group"].nunique()
    pr.expect("types.places_mixed", int(((mixed > 1) & (places.set_index("place_ref")["n_records"].reindex(mixed.index) >= 2)).sum()), EXPECT["types.places_mixed"])
    pr.expect("types.records", int(pd.to_numeric(groups["n_records"]).sum()), EXPECT["types.records"])
    pr.expect("types.n_operator_types", len(groups), EXPECT["types.n_operator_types"])

    # ---- counties
    cr, layer, meta = build_counties(pts, units)
    us_n = int((pts["iso3_source"] == "USA").sum())
    cat = cr["assignment"].value_counts().reindex(ASSIGNMENTS).fillna(0).astype(int)
    pr.check(int(cat.sum()) == us_n, f"sum of categories {int(cat.sum())} differs from the number of US records {us_n}")
    pr.expect("us.total", us_n, EXPECT["us.total"])
    for k in ASSIGNMENTS:
        pr.expect(f"us.{k}", int(cat[k]), EXPECT[f"us.{k}"])
    amb_groups = sorted(cr[cr["assignment"] == "ambiguous_name"].groupby("candidates").size().tolist(), reverse=True)
    pr.expect("us.ambiguous_groups", amb_groups, EXPECT["us.ambiguous_groups"])
    cov = layer["coverage_status"] == "covered"
    nrec = pd.to_numeric(layer.loc[cov, "n_records"])
    pr.expect("county.units", len(layer), EXPECT["county.units"])
    pr.expect("county.ct_units", len(meta["ct_units"]), EXPECT["county.ct_units"])
    pr.expect("county.not_covered", int((~cov).sum()), EXPECT["county.not_covered"])
    pr.expect("county.with_records", int((nrec > 0).sum()), EXPECT["county.with_records"])
    pr.expect("county.sum", int(nrec.sum()), EXPECT["county.sum"])
    pr.check(int(nrec.sum()) == int(cat["matched"]), f"sum of n_records over covered units {int(nrec.sum())} differs from matched {int(cat['matched'])}")
    top_u = layer.loc[nrec.idxmax()]
    pr.expect("county.max", int(top_u["n_records"]), EXPECT["county.max"])
    pr.expect("county.max_unit", top_u["unit_id"], EXPECT["county.max_unit"])
    nc_units = set(layer.loc[~cov, "unit_id"])
    pr.check(not (set(cr.loc[cr["assignment"] == "matched", "unit_id"]) & nc_units), "a matched record names a not_covered unit")
    pr.check(bool((layer.loc[~cov, "coverage_note"] != "").all()), "a not_covered unit has no coverage_note")
    pr.check(bool((layer.loc[~cov, VALUE_COLS] == "").all().all()), "a not_covered unit has values")
    pr.check(bool((layer.loc[cov, "coverage_note"] == "").all()), "a covered unit has a coverage_note")

    # link to step 4: every county-precision record of 0.1.0 is `matched` to the unit it carries
    cp = pts[pts["coord_precision"] == "county"][["record_id", "unit_id"]].merge(cr[["record_id", "unit_id", "assignment"]], on="record_id",
                                                                                 how="left", suffixes=("_pts", "_cnt"))
    link_ok = int(((cp["assignment"] == "matched") & (cp["unit_id_pts"] == cp["unit_id_cnt"])).sum())
    pr.expect("link.county_precision", link_ok, EXPECT["link.county_precision"])
    pr.expect("link.county_precision_all", len(cp), link_ok)
    pr.raise_if_any()

    # ---- write
    f_places, f_layer, f_cr = "dc_atlas_count_places.csv", "dc_atlas_count_usa_adm2.csv", "county_records.csv"
    f_groups = "operator_type_groups.csv"
    (out / f_groups).write_bytes(groups_bytes)
    write_csv(places, out / f_places)
    write_csv(layer, out / f_layer)
    write_csv(cr, out / f_cr)

    # ---- report
    lines += ["", "## Places (`dc_atlas_count_places`)", "",
              f"- rows {len(places)} (expected 2 303), sum of n_records {int(n.sum())} (6 087), single-record places {int((n == 1).sum())} (1 424), "
              f"2-9 records {int(((n >= 2) & (n <= 9)).sum())} (770), 10 or more {int((n >= 10).sum())} (109)",
              f"- largest place: {top['place_name']} (`{top['place_ref']}`), {int(top['n_records'])} records",
              "- top 10 places: " + "; ".join(f"{r.place_name} {r.n_records}" for r in places.sort_values(["n_records", "record_id"], ascending=[False, True]).head(10).itertuples()),
              "", "## Operator types (`operator_type_groups.csv`)", "",
              f"- {len(groups)} operator types in {len(set(groups['type_group']))} groups; the table agrees with the points (types, numbers, sum {int(pd.to_numeric(groups['n_records']).sum())})",
              "- records with a point by group " + ", ".join(GROUPS) + ": " + " / ".join(str(int((city['type_group'] == g).sum())) for g in GROUPS),
              "- places with one record by group: " + " / ".join(str(int((places['type_group'] == g).sum())) for g in GROUPS),
              f"- places with two or more records {int((n >= 2).sum())}, of them with records of different groups {int(((mixed > 1) & (places.set_index('place_ref')['n_records'].reindex(mixed.index) >= 2)).sum())}",
              "", "## US records by assignment (`county_records.csv`)", ""]
    lines += [f"- {k}: {int(cat[k])}" for k in ASSIGNMENTS] + [f"- total: {int(cat.sum())}"]
    lines += ["", "ambiguous records by candidate set: " + "; ".join(
        f"{c.replace(';', ' / ')}: {k}" for c, k in cr[cr['assignment'] == 'ambiguous_name'].groupby('candidates').size().sort_values(ascending=False).items())]
    lines += ["", "## Counties (`dc_atlas_count_usa_adm2`)", "",
              f"- units {len(layer)}; covered {int(cov.sum())}; not_covered {int((~cov).sum())} (Connecticut {len(meta['ct_units'])}, ambiguous pairs {len(meta['amb_units'])})",
              f"- units with records {int((nrec > 0).sum())}; sum of n_records {int(nrec.sum())}; largest {top_u['name']} (`{top_u['unit_id']}`) {int(top_u['n_records'])}",
              f"- link to step 4: {link_ok} of {len(cp)} county-precision records of 0.1.0 are `matched` to their own unit",
              "- not_covered because of a shared name: " + ", ".join(f"{layer.loc[layer['unit_id'] == u, 'name'].iloc[0]} (`{u}`)" for u in sorted(meta["amb_units"]))]
    bins = [1, 3, 10, 30, 100]
    cls = [int(((nrec >= lo) & (nrec < hi)).sum()) for lo, hi in zip(bins, bins[1:] + [10 ** 9])]
    lines += [f"- display classes 1-2 / 3-9 / 10-29 / 30-99 / 100+: {' / '.join(map(str, cls))} (SPEC 3 item 5: {' / '.join(map(str, EXPECT_DISPLAY_CLASSES))}"
              f"{'' if cls == EXPECT_DISPLAY_CLASSES else '; DIFFERENT, report only'})"]
    geo = None
    if a.analysis_adm2:
        geo = point_vs_named_county(pts, cr, Path(a.analysis_adm2), [Path(m) for m in a.sources_manifest], lines)
    else:
        lines += ["", "## US records with a point: point against the named county", "", "Not run: `--analysis-adm2` was not given."]
    (out / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    outputs = {f: dict(bytes=(out / f).stat().st_size, sha256=sha256_bytes((out / f).read_bytes())) for f in (f_places, f_layer, f_cr, f_groups)}
    man = dict(version=VERSION, checked_at=a.checked_at, inputs={i["file"]: {k: i[k] for k in ("what", "bytes", "sha256", "read")} for i in (in_pts, in_units, in_groups)},
               outputs=outputs)
    if geo:
        man["inputs"]["analysis_usa_adm2.parquet"] = dict(sha256=geo["parquet_sha256"], hash_checked_against_manifest=geo["hash_checked_against_manifest"])
        man["point_vs_named_county"] = {k: geo[k] for k in ("records_with_point_and_named_county", "same_county", "other_county", "outside_all_counties")}
    (out / "sources_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Done: {f_places} {len(places)} rows, {f_layer} {len(layer)} rows, {f_cr} {len(cr)} rows; numbers of SPEC 2.4 match.")
    if geo:
        print(f"Points in another county than the record names: {geo['other_county']} of {geo['records_with_point_and_named_county']}.")


if __name__ == "__main__":
    main()
