r"""abf-index 0.1.0: build the index that links every record of the world point layers to units ADM0-ADM2 of abf-boundaries v0.2.0
(SPEC_INDEX_territory_v0_1 r5).

Indexed: Atlas (dc_atlas_points) and Epoch (dc_epoch_points) of abf-dc 0.2.0 -> set abf-dc; GEM units -> set abf-energy;
GEM units with TransitionZero ids -> set abf-energync (CC BY-NC, kept apart, P3).

Inputs (read only)
    data\abf-dc\v0.2.0\dc_atlas_points.csv, dc_epoch_points.csv, manifest.json     (repository)
    <release>\county_records.csv, operator_type_groups.csv                          (D:\GISData\release\abf-dc-v0.2.0)
    data\gem\energy_plants_gem_units.csv, energy_plants_gem_tzsam_units.csv, build_hashes.json
    data\abf-boundaries\v0.2.0\units.csv                                            (repository)
    <frame>\display\adm1.parquet, adm2.parquet and <frame>\analysis\*.parquet       (D:\GISData\Boundaries\out\abf-boundaries-v0.2.0)
    data\index\rules\atlas_adm1_countries.csv                                       (optional: Atlas regions by the field outside the USA)
Outputs (data\index\)
    <set>\<ISO3>.csv, <ISO3>.csv.gz, adm0_other.csv(.gz), summary.csv, meta.json, and index_<set>.zip (deterministic, for Zenodo)
    build_report.md, build_hashes.json

Run (from the repository root, cmd):
    python scripts\index\build_index.py

Same inputs => byte-identical outputs (P5): no times, no random order. A failed check stops the build BEFORE anything is written.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import sys
import time
import unicodedata
import warnings
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import Point, box
from shapely.ops import nearest_points

warnings.filterwarnings("ignore")
GEOD = Geod(ellps="WGS84")
INDEX_VERSION = "0.1.0"
BOUNDARY_RELEASE = "abf-boundaries-v0.2.0"
NEAR_M = 22200.0                     # SPEC 2 item 2: 12 nautical miles
EXPECTED = {"dc_atlas_points": 9865, "dc_epoch_points": 94, "energy_plants_gem_units": 164672, "energy_plants_gem_tzsam_units": 18732}
EXPECTED_US_MATCHED = 3914
EXPECTED_US_ATLAS = 4038
SOFT = {"adm1_point rows": 4, "adm0_other abf-dc": 4, "adm0_other abf-energy": 291, "adm0_other abf-energync": 102}
ANALYSIS = {1: {"USA": "USA_adm1_cb2023_500k.parquet", "NOR": "NOR_adm1_inndelingsbase_20260101.parquet"},
            2: {"USA": "USA_adm2_cb2023_500k.parquet", "NOR": "NOR_adm2_inndelingsbase_20260101.parquet"}}
NOTES = {"", "ambiguous_name", "connecticut", "no_county_field", "no_state", "region_not_matched", "region_only", "no_unit_near", "no_point", "point_in_other_country"}
COMMON = ["record_id", "layer_id", "adm0", "adm0_basis", "adm0_other", "adm1", "adm2", "unit_basis", "unit_note", "adm1_point", "adm2_point",
          "approximate", "boundary_release"]
SETFIELDS = {"abf-dc": ["name", "status_raw", "type_group", "power_class", "power_mw"],
             "abf-energy": ["plant_name", "location_id", "type", "status_group", "capacity_mw"],
             "abf-energync": ["plant_name", "location_id", "type", "status_group", "capacity_mw"]}
SETS = ["abf-dc", "abf-energy", "abf-energync"]
DEFAULT_FRAME = r"D:\GISData\Boundaries\out\abf-boundaries-v0.2.0"
DEFAULT_RELEASE = r"D:\GISData\release\abf-dc-v0.2.0"


class Stop(Exception):
    pass


def log(s: str = "") -> None:
    print(s, flush=True)


def norm(s) -> str:
    """Name normalisation (same as dc_lib.norm of abf-dc): NFKD, no diacritics, casefold, non-alphanumerics -> one space, St/Ste -> saint/sainte."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"\bst\b\.?", "saint", s)
    s = re.sub(r"\bste\b\.?", "sainte", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def sha_pair(p: Path) -> dict:
    """SHA-256 of the file as it lies and of the file with CRLF -> LF (Windows working copies of git files)."""
    h, hl, carry, n = hashlib.sha256(), hashlib.sha256(), b"", 0
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            n += len(chunk)
            h.update(chunk)
            data = carry + chunk
            if data.endswith(b"\r"):
                carry, data = b"\r", data[:-1]
            else:
                carry = b""
            hl.update(data.replace(b"\r\n", b"\n"))
    hl.update(carry)
    return {"bytes": n, "sha256": h.hexdigest(), "sha256_lf": hl.hexdigest()}


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def rcsv(p: Path, need: list[str]) -> pd.DataFrame:
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8")
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise Stop(f"{p.name}: columns {miss} not found; columns are {list(df.columns)}")
    return df


def walk_shas(o, acc: set) -> set:
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "sha256" and isinstance(v, str):
                acc.add(v)
            walk_shas(v, acc)
    elif isinstance(o, list):
        for v in o:
            walk_shas(v, acc)
    return acc


# ------------------------------------------------------------------------------------------------ geometry
def read_geo(p: Path) -> gpd.GeoDataFrame:
    g = gpd.read_parquet(p)
    if "unit_id" not in g.columns:
        g = g.reset_index()
    if "unit_id" not in g.columns:
        raise Stop(f"{p.name}: no unit_id column; columns are {list(g.columns)}")
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    return g[["unit_id", "geometry"]].reset_index(drop=True)


class Frame:
    """Units of the frame per country and level. Geometry: computed (analysis) where the frame has it, else display."""

    def __init__(self, units: pd.DataFrame, froot: Path):
        self.units = units
        self.iso = dict(zip(units["unit_id"], units["iso3"]))
        self.parent = dict(zip(units["unit_id"], units["parent_id"]))
        self.name = dict(zip(units["unit_id"], units["name"]))
        self.level = dict(zip(units["unit_id"], units["level"]))
        self.adm0 = set(units.loc[units["level"] == "ADM0", "unit_id"])
        self.has = {1: set(units.loc[units["level"] == "ADM1", "iso3"]), 2: set(units.loc[units["level"] == "ADM2", "iso3"])}
        self.geometry_note: dict[int, dict[str, str]] = {1: {}, 2: {}}
        self.polys: dict[int, dict[str, gpd.GeoDataFrame]] = {1: {}, 2: {}}
        self.polys_display: dict[int, dict[str, gpd.GeoDataFrame]] = {1: {}, 2: {}}
        for lev in (1, 2):
            disp = read_geo(froot / "display" / f"adm{lev}.parquet")
            want = set(units.loc[units["level"] == f"ADM{lev}", "unit_id"])
            if set(disp["unit_id"]) != want:
                raise Stop(f"display/adm{lev}.parquet: unit_id set differs from units.csv ({len(set(disp['unit_id']) ^ want)} units)")
            use = disp
            for c, fn in ANALYSIS[lev].items():
                p = froot / "analysis" / fn
                ids = set(units.loc[(units["level"] == f"ADM{lev}") & (units["iso3"] == c), "unit_id"])
                if p.is_file():
                    a = read_geo(p)
                    extra = set(a["unit_id"]) - ids
                    if extra:
                        raise Stop(f"analysis/{fn}: {len(extra)} unit_id not in units.csv for {c}: {sorted(extra)[:5]}")
                    left = sorted(ids - set(a["unit_id"]))          # units the computed file does not have keep the display geometry
                    keep = disp[disp["unit_id"].isin(left)]
                    use = pd.concat([use[~use["unit_id"].isin(ids)], a, keep], ignore_index=True)
                    self.geometry_note[lev][c] = f"analysis/{fn}" + (f" ({len(left)} unit(s) from display: {', '.join(left)})" if left else "")
                else:
                    self.geometry_note[lev][c] = f"display/adm{lev}.parquet (analysis file {fn} not found)"
            for tab, store in ((use, self.polys[lev]), (disp, self.polys_display[lev])):
                tab = tab.assign(iso3=tab["unit_id"].map(self.iso))
                for c in sorted(set(tab["iso3"])):
                    g = tab[tab["iso3"] == c][["unit_id", "geometry"]].sort_values("unit_id").reset_index(drop=True)
                    store[c] = gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326")


def locate_in(lon: np.ndarray, lat: np.ndarray, g: gpd.GeoDataFrame):
    """Points -> unit of ONE country: strictly within (lowest unit_id if polygons overlap), else the nearest unit within 22.2 km (geodesic).
    -> unit ids (object array, '' = none), how ('within'/'near'/''), n of points with several hits."""
    n = len(lon)
    uid, how = np.full(n, "", dtype=object), np.full(n, "", dtype=object)
    if n == 0:
        return uid, how, 0
    d = pd.DataFrame({"lon": lon, "lat": lat})
    gid = d.groupby(["lon", "lat"], sort=False).ngroup().to_numpy()
    first = np.unique(gid, return_index=True)[1]
    ul, ua = lon[first], lat[first]
    m = len(ul)
    u_uid, u_how = np.full(m, "", dtype=object), np.full(m, "", dtype=object)
    pts = gpd.GeoDataFrame({"i": np.arange(m)}, geometry=gpd.points_from_xy(ul, ua), crs="EPSG:4326")
    j = gpd.sjoin(pts, g[["unit_id", "geometry"]], how="inner", predicate="within")
    multi = int((j.groupby("i").size() > 1).sum()) if len(j) else 0
    j = j.sort_values(["i", "unit_id"]).drop_duplicates("i")
    u_uid[j["i"].to_numpy()] = j["unit_id"].to_numpy()
    u_how[j["i"].to_numpy()] = "within"
    geoms, ids = g.geometry.to_numpy(), g["unit_id"].to_numpy()
    sidx = g.sindex
    for i in np.where(u_how == "")[0]:
        dlat = 0.25
        dlon = min(0.25 / max(math.cos(math.radians(ua[i])), 0.05), 180.0)
        cand = sidx.query(box(ul[i] - dlon, ua[i] - dlat, ul[i] + dlon, ua[i] + dlat))
        best = None
        p = Point(ul[i], ua[i])
        for c in cand:
            a, b = nearest_points(geoms[c], p)
            dm = GEOD.inv(a.x, a.y, b.x, b.y)[2]
            key = (dm, ids[c])
            if best is None or key < best:
                best = key
        if best is not None and best[0] <= NEAR_M:
            u_uid[i], u_how[i] = best[1], "near"
    return u_uid[gid], u_how[gid], multi


def point_chain(lon, lat, country, polys, parent, has, only=None):
    """Unit of the point inside the country `country[i]` (SPEC 2 item 2). ADM2 first where the country has it (ADM1 = its parent),
    else ADM1. Returns u1, u2 (object arrays), counters."""
    n = len(lon)
    u1, u2 = np.full(n, "", dtype=object), np.full(n, "", dtype=object)
    h1, h2 = np.full(n, "", dtype=object), np.full(n, "", dtype=object)
    stats = Counter()
    ok = ~np.isnan(lon) & ~np.isnan(lat)
    for c in sorted(set(country[ok])):
        if only is not None and c not in only:
            continue
        idx = np.where(ok & (country == c))[0]
        if c in polys[2]:
            a, b, mm = locate_in(lon[idx], lat[idx], polys[2][c])
            u2[idx], h2[idx] = a, b
            stats["multi_hit_adm2"] += mm
        if c in polys[1]:
            a, b, mm = locate_in(lon[idx], lat[idx], polys[1][c])
            stats["multi_hit_adm1"] += mm
            have2 = u2[idx] != ""
            par = np.array([parent.get(x, "") for x in u2[idx]], dtype=object)
            dis = have2 & (a != "") & (par != a)
            stats[f"adm1_vs_parent_of_adm2_disagree:{c}"] += int(dis.sum())
            res = np.where(have2, par, a)
            u1[idx] = res
            h1[idx] = np.where(have2, h2[idx], b)
        elif c in polys[2]:
            u1[idx] = [parent.get(x, "") for x in u2[idx]]
            h1[idx] = h2[idx]
    return u1, u2, h1, h2, stats


# ------------------------------------------------------------------------------------------------ main build
def main() -> int:
    t0 = time.time()
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(root))
    ap.add_argument("--frame-root", default=DEFAULT_FRAME)
    ap.add_argument("--release", default=DEFAULT_RELEASE)
    ap.add_argument("--gem-dir", default=None, help="folder with the GEM build (default <repo>\\data\\gem); needed when the branch checked out has no data\\gem")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--rules", default=None, help="atlas_adm1_countries.csv (default <out-dir>\\rules\\atlas_adm1_countries.csv, optional)")
    ap.add_argument("--no-sha-check", action="store_true", help="tests only")
    ap.add_argument("--no-count-check", action="store_true", help="tests only: skip the expected record counts")
    a = ap.parse_args()
    repo, froot, rel = Path(a.repo), Path(a.frame_root), Path(a.release)
    out_dir = Path(a.out_dir) if a.out_dir else repo / "data" / "index"
    rules_p = Path(a.rules) if a.rules else out_dir / "rules" / "atlas_adm1_countries.csv"
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "", hard: bool = True):
        checks.append((name, bool(ok), detail))
        log(f"  [{'OK' if ok else ('STOP' if hard else 'NOTE')}] {name}: {detail}")
        if hard and not ok:
            raise Stop(f"check failed: {name}: {detail}")

    try:
        # ---------------------------------------------------------------- inputs
        log("== inputs")
        dcd, gd = repo / "data" / "abf-dc" / "v0.2.0", (Path(a.gem_dir) if a.gem_dir else repo / "data" / "gem")
        paths = {"dc_atlas_points.csv": dcd / "dc_atlas_points.csv", "dc_epoch_points.csv": dcd / "dc_epoch_points.csv",
                 "abf-dc manifest.json": dcd / "manifest.json", "county_records.csv": rel / "county_records.csv",
                 "operator_type_groups.csv": rel / "operator_type_groups.csv",
                 "energy_plants_gem_units.csv": gd / "energy_plants_gem_units.csv",
                 "energy_plants_gem_tzsam_units.csv": gd / "energy_plants_gem_tzsam_units.csv", "gem build_hashes.json": gd / "build_hashes.json",
                 "units.csv": repo / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"}
        if rules_p.is_file():
            paths["atlas_adm1_countries.csv"] = rules_p
        inputs = {}
        for k, p in paths.items():
            if not p.is_file():
                raise Stop(f"input not found: {p}")
            inputs[k] = {"path": str(p), **sha_pair(p)}
            log(f"  {k}: {inputs[k]['bytes']:,} bytes, sha256 {inputs[k]['sha256'][:16]}..., sha256_lf {inputs[k]['sha256_lf'][:16]}...")
        man = json.loads(paths["abf-dc manifest.json"].read_text(encoding="utf-8"))
        man_csv = {l["layer_id"]: l["files"]["csv"]["sha256"] for l in man["layers"] if "csv" in l.get("files", {})}
        man_all = walk_shas(man, set())
        bh = json.loads(paths["gem build_hashes.json"].read_text(encoding="utf-8"))
        if not a.no_sha_check:
            for lid, fn in (("dc_atlas_points", "dc_atlas_points.csv"), ("dc_epoch_points", "dc_epoch_points.csv")):
                check(f"sha256_lf of {fn} = manifest.json of abf-dc 0.2.0", inputs[fn]["sha256_lf"] == man_csv.get(lid),
                      f"file {inputs[fn]['sha256_lf'][:16]}..., manifest {str(man_csv.get(lid))[:16]}...; as it lies: {inputs[fn]['sha256'][:16]}...")
            for fn in ("county_records.csv", "operator_type_groups.csv"):
                check(f"sha256_lf of {fn} is listed in manifest.json of abf-dc 0.2.0", inputs[fn]["sha256_lf"] in man_all, inputs[fn]["sha256_lf"][:16] + "...")
            for fn in ("energy_plants_gem_units.csv", "energy_plants_gem_tzsam_units.csv"):
                check(f"sha256_lf of {fn} = files of build_hashes.json (GEM build)", inputs[fn]["sha256_lf"] == bh.get("files", {}).get(fn),
                      f"file {inputs[fn]['sha256_lf'][:16]}..., build_hashes {str(bh.get('files', {}).get(fn))[:16]}...")

        units = rcsv(paths["units.csv"], ["unit_id", "iso3", "level", "name", "parent_id"])
        atl = rcsv(paths["dc_atlas_points.csv"], ["record_id", "lon", "lat", "name", "status_raw", "operator_type", "power_class", "adm1_raw", "iso3_source", "iso3_frame"])
        epo = rcsv(paths["dc_epoch_points.csv"], ["record_id", "lon", "lat", "name", "power_mw", "iso3_source", "iso3_frame"])
        gcols = ["record_id", "location_id", "plant_name", "type", "status_group", "capacity_mw", "iso3_source", "iso3_frame", "location_accuracy", "lon", "lat"]
        gem = rcsv(paths["energy_plants_gem_units.csv"], gcols)
        gnc = rcsv(paths["energy_plants_gem_tzsam_units.csv"], gcols)
        cr = rcsv(paths["county_records.csv"], ["record_id", "unit_id", "assignment"])
        otg = rcsv(paths["operator_type_groups.csv"], ["operator_type", "type_group"])
        for nm, df, lid in (("atlas", atl, "dc_atlas_points"), ("epoch", epo, "dc_epoch_points"), ("gem", gem, "energy_plants_gem_units"),
                            ("gem_nc", gnc, "energy_plants_gem_tzsam_units")):
            check(f"records {lid}", a.no_count_check or len(df) == EXPECTED[lid], f"{len(df):,} (expected {EXPECTED[lid]:,})")
            check(f"record_id unique in {lid}", df["record_id"].is_unique)
        allid = pd.concat([atl["record_id"], epo["record_id"], gem["record_id"], gnc["record_id"]])
        check("record_id unique across the four layers", allid.is_unique)
        miss_t = sorted(set(atl["operator_type"]) - set(otg["operator_type"]))
        check("every Atlas operator_type has a group in operator_type_groups.csv", not miss_t, str(miss_t))
        gmap = dict(zip(otg["operator_type"], otg["type_group"]))

        # ---------------------------------------------------------------- frame
        log("== frame")
        F = Frame(units, froot)
        check("countries with ADM1 / ADM2 in units.csv", True, f"{len(F.has[1])} / {sorted(F.has[2])}", hard=False)
        for lev in (1, 2):
            for c, s in sorted(F.geometry_note[lev].items()):
                log(f"  ADM{lev} {c}: {s}")
        bgeom = {f"adm{lev}": {"default": f"display/adm{lev}.parquet", **{c: s for c, s in sorted(F.geometry_note[lev].items())}} for lev in (1, 2)}

        # ---------------------------------------------------------------- Atlas regions table (optional)
        table: dict[str, str] = {}
        if rules_p.is_file():
            tb = rcsv(rules_p, ["iso3", "frame_level", "decided_by"])
            skipped = []
            for r in tb.itertuples(index=False):
                lv = r.frame_level.strip().lower()
                if r.iso3 == "USA":
                    log("  note: USA in atlas_adm1_countries.csv is ignored (the US uses county_records.csv)")
                    continue
                if not r.decided_by.strip():
                    skipped.append(r.iso3)
                    continue
                if lv not in ("adm1", "adm2", "adm1_or_adm2"):
                    raise Stop(f"atlas_adm1_countries.csv: {r.iso3}: unknown frame_level {r.frame_level!r} (adm1, adm2, adm1_or_adm2)")
                if (lv in ("adm1", "adm1_or_adm2") and r.iso3 not in F.has[1]) or (lv in ("adm2", "adm1_or_adm2") and r.iso3 not in F.has[2] and lv != "adm1_or_adm2"):
                    raise Stop(f"atlas_adm1_countries.csv: {r.iso3} has no such level in the frame")
                table[r.iso3] = lv
            if skipped:
                log(f"  rows without decided_by are not applied: {skipped}")
            log(f"  Atlas regions by the field: {len(table)} countries from {rules_p.name}: {sorted(table)}")
        else:
            log("  Atlas regions table not found: Atlas outside the USA is placed by the point (rule 0.1.1 later)")
        name_idx: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for r in units.itertuples(index=False):
            if r.level in ("ADM1", "ADM2"):
                name_idx[(r.iso3, r.level)][norm(r.name)].append(r.unit_id)

        # ---------------------------------------------------------------- records
        log("== records")
        parts = []

        def part(set_, layer, kind, df, extra):
            lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(float)
            lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(float)
            bad = (np.abs(lon) > 180) | (np.abs(lat) > 90)
            if np.nansum(bad):
                raise Stop(f"{layer}: coordinates out of range")
            p = pd.DataFrame({"set": set_, "layer_id": layer, "kind": kind, "record_id": df["record_id"].to_numpy(),
                              "src": df["iso3_source"].to_numpy(), "frm": df["iso3_frame"].to_numpy(), "lon": lon, "lat": lat})
            for c in ("name", "status_raw", "type_group", "power_class", "power_mw", "plant_name", "location_id", "type", "status_group", "capacity_mw",
                      "adm1_raw", "acc"):
                p[c] = extra.get(c, "")
            parts.append(p)

        part("abf-dc", "dc_atlas_points", "atlas", atl, {"name": atl["name"].to_numpy(), "status_raw": atl["status_raw"].to_numpy(),
                                                          "type_group": atl["operator_type"].map(gmap).to_numpy(), "power_class": atl["power_class"].to_numpy(),
                                                          "adm1_raw": atl["adm1_raw"].to_numpy()})
        part("abf-dc", "dc_epoch_points", "epoch", epo, {"name": epo["name"].to_numpy(), "power_mw": epo["power_mw"].to_numpy()})
        for set_, layer, df in (("abf-energy", "energy_plants_gem_units", gem), ("abf-energync", "energy_plants_gem_tzsam_units", gnc)):
            acc = df["location_accuracy"].str.strip().str.lower()
            bad = sorted(set(acc) - {"exact", "approximate"})
            check(f"location_accuracy of {layer} is exact/approximate", not bad, str(bad))
            part(set_, layer, "gem", df, {c: df[c].to_numpy() for c in ("plant_name", "location_id", "type", "status_group", "capacity_mw")} | {"acc": acc.to_numpy()})
        R = pd.concat(parts, ignore_index=True)
        n = len(R)
        has_pt = (~np.isnan(R["lon"].to_numpy()) & ~np.isnan(R["lat"].to_numpy()))
        kind, src, frm = R["kind"].to_numpy(), R["src"].to_numpy(), R["frm"].to_numpy()
        is_atl = kind == "atlas"
        adm0 = np.where(is_atl, np.where(src != "", src, frm), np.where(frm != "", frm, src))
        basis0 = np.where(is_atl, "field", np.where(frm != "", "point", "field"))
        other = np.where((src != "") & (frm != "") & (src != frm), np.where(adm0 == frm, src, frm), "")
        bad0 = sorted({x for x in adm0 if x == "" or x not in F.adm0})
        check("adm0 is a unit ADM0 of the frame for every record", not bad0, str(bad0[:10]))
        R["adm0"], R["adm0_basis"], R["adm0_other"] = adm0, basis0, other

        # ---------------------------------------------------------------- units by point (own country only)
        log("== point lookup (only units of the own country; strictly within, then <= 22.2 km)")
        lon, lat = R["lon"].to_numpy(float), R["lat"].to_numpy(float)
        t = time.time()
        u1p, u2p, h1p, h2p, st = point_chain(lon, lat, adm0.astype(object), F.polys, F.parent, F.has)
        log(f"  own-country lookup {time.time() - t:.0f} s; {dict((k, v) for k, v in st.items() if not k.startswith('adm1_vs') and v)}")
        dis = {k.split(":")[1]: v for k, v in st.items() if k.startswith("adm1_vs") and v}
        # the point of a record whose adm0 is taken by the field and lies in another country (SPEC 2 item 3)
        oth_mask = has_pt & (basis0 == "field") & (frm != "") & (frm != adm0)
        u1o, u2o, _, _, _ = point_chain(np.where(oth_mask, lon, np.nan), np.where(oth_mask, lat, np.nan), np.where(oth_mask, frm, "").astype(object),
                                        F.polys, F.parent, F.has)

        # ---------------------------------------------------------------- the chain per record
        cr_idx = cr.set_index("record_id")
        us_state = {norm(r.name): r.unit_id for r in units[(units["iso3"] == "USA") & (units["level"] == "ADM1")].itertuples(index=False)}
        a1 = np.full(n, "", dtype=object)
        a2 = np.full(n, "", dtype=object)
        ub = np.full(n, "", dtype=object)
        un = np.full(n, "", dtype=object)
        p1 = np.full(n, "", dtype=object)
        p2 = np.full(n, "", dtype=object)
        stat = Counter()
        to_pt = np.zeros(n, dtype=bool)                    # Atlas, table country: region not matched, the row goes by the point (SPEC r5)
        rid, raw1 = R["record_id"].to_numpy(), R["adm1_raw"].to_numpy()
        for i in range(n):
            c = adm0[i]
            lv1, lv2 = c in F.has[1], c in F.has[2]
            if is_atl[i] and c == "USA":
                if rid[i] not in cr_idx.index:
                    raise Stop(f"{rid[i]}: Atlas record of the USA is not in county_records.csv")
                row = cr_idx.loc[rid[i]]
                asg = row["assignment"]
                if asg == "matched":
                    a2[i] = row["unit_id"]
                    a1[i] = F.parent.get(a2[i], "")
                    ub[i] = "field"
                else:
                    if asg not in NOTES:
                        raise Stop(f"{rid[i]}: unknown county_records assignment {asg!r}")
                    a1[i] = us_state.get(norm(raw1[i]), "") if str(raw1[i]).strip() else ""
                    ub[i] = "field" if a1[i] else ""
                    un[i] = asg
                    stat["us_state_by_field"] += 1 if a1[i] else 0
                stat[f"us_assignment:{asg}"] += 1
            elif is_atl[i] and c in table:
                lvl = table[c]
                key_ = norm(raw1[i]) if str(raw1[i]).strip() else None
                cand, clev = [], lvl
                if key_ is not None:
                    if lvl == "adm1_or_adm2":                  # the field names a department (ADM2) or a region (ADM1): ADM2 first, then ADM1
                        cand, clev = name_idx[(c, "ADM2")].get(key_, []), "adm2"
                        if len(cand) != 1:
                            cand, clev = name_idx[(c, "ADM1")].get(key_, []), "adm1"
                    else:
                        cand = name_idx[(c, lvl.upper())].get(key_, [])
                if len(cand) == 1:
                    ub[i] = "field"
                    if clev == "adm1":
                        a1[i] = cand[0]
                    else:
                        a2[i] = cand[0]
                        a1[i] = F.parent.get(cand[0], "")
                    stat[f"table_matched:{c}"] += 1
                    if clev == "adm1" and lv2:             # the record names a region, the country has ADM2: ADM2 is not added by point (one basis per row)
                        un[i] = "region_only"
                        stat[f"region_only:{c}"] += 1
                elif has_pt[i]:                            # region not matched, but there is a point: the whole row by the point, note empty
                    a1[i], a2[i] = u1p[i], u2p[i]
                    to_pt[i] = True
                    if a1[i] or a2[i]:
                        ub[i] = "point"
                    if (lv2 and not a2[i]) or (lv1 and not a1[i]):
                        un[i] = "no_unit_near"
                    stat[f"table_not_matched_to_point:{c}"] += 1
                else:
                    un[i] = "region_not_matched"
                    stat[f"table_not_matched:{c}"] += 1
            else:
                if not (lv1 or lv2):
                    pass                                   # the frame has no unit level for this country: empty, no note (P2)
                elif not has_pt[i]:
                    un[i] = "no_point"
                else:
                    a1[i], a2[i] = u1p[i], u2p[i]
                    ub[i] = "point" if (a1[i] or a2[i]) else ""
                    if (lv2 and not a2[i]) or (lv1 and not a1[i]):
                        un[i] = "no_unit_near"
            if oth_mask[i]:
                p1[i], p2[i] = u1o[i], u2o[i]
                un[i] = "point_in_other_country"
        R["adm1"], R["adm2"], R["unit_basis"], R["unit_note"], R["adm1_point"], R["adm2_point"] = a1, a2, ub, un, p1, p2
        R["to_point"] = to_pt
        R["approximate"] = np.where(~has_pt, "", np.where(kind == "gem", np.where(R["acc"].to_numpy() == "approximate", "true", "false"), "true"))
        R["boundary_release"] = BOUNDARY_RELEASE

        # ---------------------------------------------------------------- checks on the chain
        log("== checks")
        okc = True
        for col in ("adm1", "adm2"):
            v = R[col].to_numpy()
            ok_ = all((x == "") or (F.iso.get(x) == c) for x, c in zip(v, adm0))
            okc &= ok_
            check(f"every {col} lies in the adm0 of its record", ok_)
        ok_ = all((x == "") or (F.iso.get(x) == o) for x, o in zip(R["adm1_point"].to_numpy(), other)) and \
            all((x == "") or (F.iso.get(x) == o) for x, o in zip(R["adm2_point"].to_numpy(), other))
        check("every adm1_point / adm2_point lies in adm0_other", ok_)
        ok_ = all(x == "" or F.parent.get(x) == y for x, y in zip(a2, a1))
        check("every adm2 has its parent as adm1", ok_)
        check("unit_note values are in the SPEC list", set(un) <= NOTES, str(sorted(set(un) - NOTES)))
        check("unit_basis = field/point/empty", set(ub) <= {"", "field", "point"})
        check("adm1_point rows (Atlas, point in another country)", int((R["adm1_point"] != "").sum()) == SOFT["adm1_point rows"],
              f"{int((R['adm1_point'] != '').sum())} (pre-flight: {SOFT['adm1_point rows']})", hard=False)
        for s_ in SETS:
            nn = int(((R["set"] == s_) & (R["adm0_other"] != "")).sum())
            check(f"adm0_other rows {s_}", nn == SOFT[f"adm0_other {s_}"], f"{nn} (pre-flight: {SOFT[f'adm0_other {s_}']})", hard=False)
        usa = R[(R["kind"] == "atlas") & (R["adm0"] == "USA")]
        m_ = cr.set_index("record_id")
        mt = usa[usa["adm2"] != ""]
        ok_ = (len(mt) == EXPECTED_US_MATCHED or a.no_count_check) and all(m_.loc[r_, "unit_id"] == u_ and m_.loc[r_, "assignment"] == "matched"
                                                                          for r_, u_ in zip(mt["record_id"], mt["adm2"]))
        check("Atlas USA: adm2 = county_records.csv on all matched records", ok_, f"{len(mt)} records with adm2 (expected {EXPECTED_US_MATCHED})")
        ok_ = (len(usa) == EXPECTED_US_ATLAS) or a.no_count_check
        check("Atlas USA records", ok_, f"{len(usa)} (expected {EXPECTED_US_ATLAS})")
        if table:
            tb_ = R[(R["kind"] == "atlas") & R["adm0"].isin(table.keys()) & (R["unit_note"] != "point_in_other_country")]
            hp_ = tb_["lon"].notna().to_numpy() & tb_["lat"].notna().to_numpy()
            ok_ = all(((x == "field") and (n_ in ("", "region_only"))) or ((x == "point") and n_ == "") or
                      ((x == "") and ((n_ == "region_not_matched" and not h_) or (n_ == "no_unit_near" and h_))) or ((x == "") and n_ == "" and not (lv_))
                      for x, n_, h_, lv_ in zip(tb_["unit_basis"], tb_["unit_note"], hp_, [c_ in F.has[1] or c_ in F.has[2] for c_ in tb_["adm0"]]))
            check("Atlas in table countries: field (note empty or region_only) / point (note empty) / empty (region_not_matched without a point, no_unit_near with one)", ok_)
            check("region_only only where the record is by the field and the country has ADM2 (adm2 empty)",
                  all((nn != "region_only") or (ub_ == "field" and a2_ == "" and c_ in F.has[2]) for nn, ub_, a2_, c_ in zip(un, ub, a2, adm0)))
            ntp, nro = int(to_pt.sum()), int((np.array(un, dtype=object) == "region_only").sum())
            log(f"  Atlas, table countries: region not matched, row moved to the point: {ntp}; region_only: {nro}")

        # Q5: computed geometry (USA, NOR) against display geometry
        diff = {}
        dsp_c = {"USA", "NOR"}
        dpolys = {1: {c: g for c, g in F.polys_display[1].items() if c in dsp_c}, 2: {c: g for c, g in F.polys_display[2].items() if c in dsp_c}}
        d1, d2, _, _, _ = point_chain(lon, lat, adm0.astype(object), dpolys, F.parent, F.has, only=dsp_c)
        sel = (ub == "point") & np.isin(adm0, list(dsp_c))
        for s_ in SETS:
            ms = sel & (R["set"].to_numpy() == s_)
            diff[s_] = {"points": int(ms.sum()), "adm1_differs": int((a1[ms] != d1[ms]).sum()), "adm2_differs": int((a2[ms] != d2[ms]).sum())}
        log(f"  computed vs display geometry (USA, NOR; rows placed by point): {diff}")

        # ---------------------------------------------------------------- serialise
        log("== serialise")
        files: dict[str, bytes] = {}
        per_set = {}
        fsize = []
        for s_ in SETS:
            S = R[R["set"] == s_].copy()
            lorder = {"dc_atlas_points": 0, "dc_epoch_points": 1}
            S["_lo"] = S["layer_id"].map(lorder).fillna(0)
            S = S.sort_values(["_lo", "record_id"], kind="stable")
            cols = COMMON + SETFIELDS[s_]
            S_out = S[cols]
            names = {}
            rows_by = {}
            for c, g in S_out.groupby("adm0", sort=True):
                names[c] = f"{s_}/{c}.csv"
                body = g.to_csv(index=False, lineterminator="\n").encode("utf-8")
                files[names[c]] = body
                files[f"{s_}/{c}.csv.gz"] = gzip.compress(body, compresslevel=9, mtime=0)
                rows_by[c] = len(g)
                fsize.append((s_, c, len(g), len(body), len(files[f"{s_}/{c}.csv.gz"])))
            og = S_out[S_out["adm0_other"] != ""]
            body = og.to_csv(index=False, lineterminator="\n").encode("utf-8")
            files[f"{s_}/adm0_other.csv"] = body
            files[f"{s_}/adm0_other.csv.gz"] = gzip.compress(body, compresslevel=9, mtime=0)
            # summary.csv
            rows = []
            for c, g in S.groupby("adm0", sort=True):
                r_ = dict(adm0=c, records=len(g), with_point=int((g["lon"].notna()).sum()), approximate_true=int((g["approximate"] == "true").sum()),
                          adm0_basis_field=int((g["adm0_basis"] == "field").sum()), adm0_other=int((g["adm0_other"] != "").sum()),
                          adm1_filled=int((g["adm1"] != "").sum()), adm2_filled=int((g["adm2"] != "").sum()),
                          unit_basis_field=int((g["unit_basis"] == "field").sum()), unit_basis_point=int((g["unit_basis"] == "point").sum()),
                          adm1_point_filled=int((g["adm1_point"] != "").sum()))
                if s_ == "abf-dc":
                    pm = pd.to_numeric(g.loc[g["layer_id"] == "dc_epoch_points", "power_mw"], errors="coerce").dropna()
                    r_["sum_epoch_power_mw"] = f"{math.fsum(pm):.3f}"
                else:
                    r_["sum_capacity_mw"] = f"{math.fsum(pd.to_numeric(g['capacity_mw'])):.3f}"
                rows.append(r_)
            files[f"{s_}/summary.csv"] = pd.DataFrame(rows).to_csv(index=False, lineterminator="\n").encode("utf-8")
            per_set[s_] = dict(S=S, rows_by=rows_by)

        # read the written bytes back: row counts, record_ids, GEM sums
        for s_ in SETS:
            back = pd.concat([pd.read_csv(io.BytesIO(files[f"{s_}/{c}.csv"]), dtype=str, keep_default_na=False) for c in per_set[s_]["rows_by"]], ignore_index=True)
            src_ids = set(R.loc[R["set"] == s_, "record_id"])
            check(f"{s_}: every record is in exactly one country file", len(back) == len(src_ids) and set(back["record_id"]) == src_ids,
                  f"{len(back):,} rows, {len(src_ids):,} records")
            if s_ != "abf-dc":
                src_df = gem if s_ == "abf-energy" else gnc
                sa = src_df.assign(mw=pd.to_numeric(src_df["capacity_mw"])).groupby(["type", "status_group"])["mw"].apply(lambda s: math.fsum(s)).to_dict()
                bk = back.assign(mw=pd.to_numeric(back["capacity_mw"])).groupby(["type", "status_group"])["mw"].apply(lambda s: math.fsum(s)).to_dict()
                check(f"{s_}: sum of capacity_mw by type x status_group equals the source", sa == bk, f"{len(sa)} groups")
            else:
                ea = math.fsum(pd.to_numeric(epo["power_mw"], errors="coerce").dropna())
                eb = math.fsum(pd.to_numeric(back.loc[back["layer_id"] == "dc_epoch_points", "power_mw"], errors="coerce").dropna())
                check("abf-dc: sum of Epoch power_mw equals the source", ea == eb, f"{ea:,.3f} MW")
                ca = Counter(atl["status_raw"])
                cb = Counter(back.loc[back["layer_id"] == "dc_atlas_points", "status_raw"])
                check("abf-dc: Atlas records by status_raw equal the source", ca == cb)
            by_c = back.groupby("adm0").size().to_dict()
            check(f"{s_}: rows per country file match", by_c == per_set[s_]["rows_by"])
        big = [f for f in fsize if f[3] > 45 * 1048576]
        check("every country CSV is at most 45 MiB (git)", not big, str(big[:3]))

        # meta.json and zip per set
        levels = {c: {"adm1": c in F.has[1], "adm2": c in F.has[2]} for c in sorted(set(R["adm0"]))}
        agg = {"abf-dc": {"atlas": {"layer_id": "dc_atlas_points", "count": "records",
                                    "by": ["status_raw", "type_group", "power_class"], "note": "Atlas has no MW; counts only."},
                          "epoch": {"layer_id": "dc_epoch_points", "count": "sites",
                                    "sum": {"field": "power_mw", "label": "sum of Epoch site IT power", "only": "dc_epoch_points"}}},
               "abf-energy": {"blocks": {"count": "records", "by": ["type", "status_group"]},
                              "sum": {"field": "capacity_mw", "within": ["type", "status_group"]},
                              "stations": {"count_distinct": "location_id", "additive_up_the_chain": False}},
               "abf-energync": {"blocks": {"count": "records", "by": ["type", "status_group"]},
                                "sum": {"field": "capacity_mw", "within": ["type", "status_group"]},
                                "stations": {"count_distinct": "location_id", "additive_up_the_chain": False}}}
        for s_ in SETS:
            S = per_set[s_]["S"]
            meta = {"schema_version": "abf-index-meta-1.0", "dataset": "abf-index" if s_ != "abf-energync" else "abf-energync (index)", "set": s_,
                    "index_version": INDEX_VERSION, "boundary_release": BOUNDARY_RELEASE, "boundary_geometry": bgeom,
                    "layers": {l: int((S["layer_id"] == l).sum()) for l in sorted(set(S["layer_id"]))},
                    "records": len(S), "near_rule_m": NEAR_M, "unit_note_values": sorted(NOTES - {""}),
                    "levels_by_country": levels, "aggregations": agg[s_],
                    "atlas_regions_by_field_countries": sorted(table) if s_ == "abf-dc" else None,
                    "files": {c: {"rows": r, "csv_bytes": len(files[f"{s_}/{c}.csv"]), "csv_gz_bytes": len(files[f"{s_}/{c}.csv.gz"]),
                                  "sha256": sha_bytes(files[f"{s_}/{c}.csv"])} for c, r in sorted(per_set[s_]["rows_by"].items())},
                    "inputs_sha256_lf": {k: v["sha256_lf"] for k, v in sorted(inputs.items())}}
            files[f"{s_}/meta.json"] = (json.dumps(meta, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            zname = f"{s_}/index_{s_}.zip"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
                zl = sorted([k for k in files if k.startswith(s_ + "/") and (k.endswith(".csv.gz") or k.endswith("summary.csv") or k.endswith("meta.json")
                                                                              or k.endswith("adm0_other.csv"))])
                for k in zl:
                    zi = zipfile.ZipInfo(k.split("/", 1)[1], date_time=(1980, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_STORED
                    zi.external_attr = 0o644 << 16
                    z.writestr(zi, files[k])
            files[zname] = buf.getvalue()

        # ---------------------------------------------------------------- rerun comparison, write
        hashes = {k: sha_bytes(v) for k, v in sorted(files.items())}
        hpath = out_dir / "build_hashes.json"
        prev = json.loads(hpath.read_text(encoding="utf-8")) if hpath.is_file() else None
        same = None if prev is None else prev.get("files") == hashes
        report = make_report(a, inputs, checks, R, per_set, fsize, hashes, diff, dis, table, F, same, time.time() - t0)
        out_dir.mkdir(parents=True, exist_ok=True)
        for k, v in files.items():
            p = out_dir / k
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(v)
        (out_dir / "build_report.md").write_bytes(report.encode("utf-8"))
        hpath.write_bytes((json.dumps({"inputs": {k: {kk: vv for kk, vv in v.items() if kk != "path"} for k, v in sorted(inputs.items())},
                                       "files": hashes}, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        log(f"== done in {time.time() - t0:.0f} s; rerun identical to the previous build: {same}; {len(files)} files in {out_dir}")
        return 0
    except Stop as e:
        log("")
        log(f"STOP: {e}")
        log("Nothing was written.")
        return 1


def make_report(a, inputs, checks, R, per_set, fsize, hashes, diff, dis, table, F, same, secs) -> str:
    L = ["# abf-index 0.1.0 · build report", "", f"Index version {INDEX_VERSION}; frame {BOUNDARY_RELEASE}; rule: SPEC_INDEX_territory_v0_1 r5.", "",
         "## Inputs", "", "| Input | Bytes | sha256 (as it lies) | sha256_lf |", "|---|---:|---|---|"]
    for k, v in sorted(inputs.items()):
        L.append(f"| {k} | {v['bytes']:,} | `{v['sha256']}` | `{v['sha256_lf']}` |")
    L += ["", "## Checks", ""] + [f"- {'OK' if ok else 'NOTE'} · {nm}: {d}" for nm, ok, d in checks]
    L += ["", "## Records", "", "| Set | Layer | Records | with point | adm0 by point | adm0 by field | adm0_other | adm1 filled | adm2 filled | approximate |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for (s_, l), g in R.groupby(["set", "layer_id"], sort=False):
        L.append(f"| {s_} | {l} | {len(g):,} | {int(g['lon'].notna().sum()):,} | {int((g['adm0_basis'] == 'point').sum()):,} | {int((g['adm0_basis'] == 'field').sum()):,} | "
                 f"{int((g['adm0_other'] != '').sum()):,} | {int((g['adm1'] != '').sum()):,} | {int((g['adm2'] != '').sum()):,} | {int((g['approximate'] == 'true').sum()):,} |")
    L += ["", "## unit_basis and unit_note", "", "| Set | Layer | field | point | empty | " + " | ".join(sorted(NOTES - {''})) + " |",
          "|---|---|---:|---:|---:|" + "---:|" * (len(NOTES) - 1)]
    for (s_, l), g in R.groupby(["set", "layer_id"], sort=False):
        L.append(f"| {s_} | {l} | {int((g['unit_basis'] == 'field').sum()):,} | {int((g['unit_basis'] == 'point').sum()):,} | {int((g['unit_basis'] == '').sum()):,} | " +
                 " | ".join(str(int((g['unit_note'] == nn).sum())) for nn in sorted(NOTES - {''})) + " |")
    L += ["", "unit_note is empty when the frame has no unit level for the country (P2) or when the unit was found.", ""]
    if table:
        L += ["## Atlas regions by the field (table countries)", "", "| Country | matched (field) | region_only | region not matched: by point | region_not_matched (no point) |", "|---|---:|---:|---:|---:|"]
        A = R[(R["kind"] == "atlas") & R["adm0"].isin(table)]
        for c in sorted(table):
            g = A[A["adm0"] == c]
            L.append(f"| {c} ({table[c]}) | {int((g['unit_basis'] == 'field').sum())} | {int((g['unit_note'] == 'region_only').sum())} | "
                     f"{int(g['to_point'].sum())} | {int((g['unit_note'] == 'region_not_matched').sum())} |")
        L += ["", f"Total: region not matched and the row moved to the point: {int(A['to_point'].sum())}; region_only: {int((A['unit_note'] == 'region_only').sum())}; "
                  f"region_not_matched without a point: {int((A['unit_note'] == 'region_not_matched').sum())}.", ""]
    L += ["## Rows with adm1_point (Atlas: adm0 by the field, point in another country)", "", "| record_id | adm0 | adm0_other | adm1_point | adm2_point |", "|---|---|---|---|---|"]
    for r in R[R["adm1_point"] != ""].itertuples(index=False):
        L.append(f"| {r.record_id} | {r.adm0} | {r.adm0_other} | {r.adm1_point} | {r.adm2_point} |")
    L += ["", "## Geometry: computed (USA, NOR) against display", "", "Rows placed by point in USA / NOR whose unit differs between the two geometries:", "",
          "| Set | rows in USA/NOR by point | adm1 differs | adm2 differs |", "|---|---:|---:|---:|"]
    for s_, d in diff.items():
        L.append(f"| {s_} | {d['points']:,} | {d['adm1_differs']:,} | {d['adm2_differs']:,} |")
    if dis:
        L += ["", f"ADM1 looked up directly differs from the parent of the ADM2 found (point rows): {dis}"]
    L += ["", "## File sizes (country files)", "", "| Set | Files | Rows | CSV MiB | gzip MiB | largest CSV (country, MiB) | largest gzip MiB |", "|---|---:|---:|---:|---:|---|---:|"]
    for s_ in SETS:
        f = [x for x in fsize if x[0] == s_]
        top = max(f, key=lambda x: x[3])
        L.append(f"| {s_} | {len(f)} | {sum(x[2] for x in f):,} | {sum(x[3] for x in f) / 1048576:.1f} | {sum(x[4] for x in f) / 1048576:.1f} | "
                 f"{top[1]} {top[3] / 1048576:.2f} | {max(x[4] for x in f) / 1048576:.2f} |")
    L += ["", "Ten largest country files (CSV bytes / gzip bytes):", "", "| Set | Country | Rows | CSV | gzip |", "|---|---|---:|---:|---:|"]
    for x in sorted(fsize, key=lambda x: -x[3])[:10]:
        L.append(f"| {x[0]} | {x[1]} | {x[2]:,} | {x[3]:,} | {x[4]:,} |")
    L += ["", "## Output files and SHA-256", "", "| File | sha256 |", "|---|---|"]
    for k, h in sorted(hashes.items()):
        if k.endswith(".zip") or k.endswith("summary.csv") or k.endswith("meta.json") or k.endswith("adm0_other.csv"):
            L.append(f"| {k} | `{h}` |")
    L += ["", f"All {len(hashes)} output files with SHA-256 are in `build_hashes.json` (country files, `.csv.gz`, summary, meta, zip).", "",
          f"Rerun against the previous `build_hashes.json`: {'no previous file' if same is None else ('identical' if same else 'DIFFERENT')}.",
          f"Build time {secs:.0f} s.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
