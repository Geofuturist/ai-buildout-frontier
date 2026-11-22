r"""abf-index 0.2.0: build the index that links every record of the world point layers to units ADM0-ADM2 of abf-boundaries v0.3.0
(SPEC_INDEX_territory_v0_1 r11 + SPEC_INDEX_territory_v0_2 r3).

Indexed: Atlas (dc_atlas_points) and Epoch (dc_epoch_points) of abf-dc 0.2.0 -> set abf-dc; GEM units -> set abf-energy;
GEM units with TransitionZero ids -> set abf-energync (CC BY-NC, kept apart, P3).

Inputs (read only)
    data\abf-dc\v0.2.0\dc_atlas_points.csv, dc_epoch_points.csv, manifest.json     (repository)
    <release>\county_records.csv, operator_type_groups.csv                          (D:\GISData\release\abf-dc-v0.2.0)
    data\gem\energy_plants_gem_units.csv, energy_plants_gem_tzsam_units.csv, build_hashes.json
    <frame>\units.csv, manifest.json, adm1.parquet, adm2.parquet, analysis_<iso>_adm<n>.parquet   (the published release D:\GISData\release\abf-boundaries-v0.3.0)
    data\index\rules\atlas_adm1_countries.csv                                       (Atlas regions by the field outside the USA)
    data\index\rules\atlas_adm1_aliases.csv                                         (spellings of Atlas regions, checked against the points)
    <prev-index>\<set>\<ISO3>.csv and build_hashes.json                              (index 0.1.x, for the regression check)
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
INDEX_VERSION = "0.2.0"
BOUNDARY_RELEASE = "abf-boundaries-v0.3.0"
OLD_BOUNDARY_RELEASE = "abf-boundaries-v0.2.0"
NEAR_M = 22200.0                     # SPEC 2 item 2: 12 nautical miles
EXPECTED = {"dc_atlas_points": 9865, "dc_epoch_points": 94, "energy_plants_gem_units": 164672, "energy_plants_gem_tzsam_units": 18732}
EXPECTED_US_MATCHED = 3914
EXPECTED_US_ATLAS = 4038
SOFT = {"adm1_point rows": 4, "adm0_other abf-dc": 4, "adm0_other abf-energy": 291, "adm0_other abf-energync": 102}
NEW15 = ["COL", "EST", "HKG", "IDN", "IRL", "KOR", "LUX", "LVA", "MEX", "NZL", "PER", "PHL", "THA", "TWN", "VNM"]
EXPECTED_ANALYSIS = {1: sorted(NEW15 + ["USA", "NOR"]), 2: ["NOR", "USA"]}      # computed files of the release
EXPECTED_UNITS = {"ADM0": 242, "ADM1": 2092, "ADM2": 3602}
EXPECTED_TABLE_COUNTRIES = 48          # 34 of index 0.1 + COL EST HKG IDN IRL KOR LUX LVA MEX NZL PER PHL THA VNM (ARCH7 21.11)
EXPECTED_ALIAS_ROWS = 59
EXPECTED_ALIAS_CHANGED_OLD = 19        # records of the countries outside the 15 that the spelling table changes (BRA, FIN, FRA, JPN, MYS, NGA)
CMP_COLS = ["adm0", "adm0_basis", "adm0_other", "adm1", "adm2", "unit_basis", "unit_note", "adm1_point", "adm2_point"]
NOTES = {"", "ambiguous_name", "connecticut", "no_county_field", "no_state", "region_not_matched", "region_only", "no_unit_near", "no_point", "point_in_other_country"}
COMMON = ["record_id", "layer_id", "adm0", "adm0_basis", "adm0_other", "adm1", "adm2", "unit_basis", "unit_note", "adm1_point", "adm2_point",
          "approximate", "boundary_release"]
SETFIELDS = {"abf-dc": ["name", "status_raw", "type_group", "power_class", "power_mw"],
             "abf-energy": ["plant_name", "location_id", "type", "status_group", "capacity_mw"],
             "abf-energync": ["plant_name", "location_id", "type", "status_group", "capacity_mw"]}
SETS = ["abf-dc", "abf-energy", "abf-energync"]
DEFAULT_FRAME = r"D:\GISData\release\abf-boundaries-v0.3.0"
DEFAULT_PREV = r"C:\Users\PGS\Documents\AI\index_work\data\index"
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


def manifest_entries(m) -> dict[str, str]:
    """path -> sha256 of every file a release manifest lists (the layout of the manifest is not assumed)."""
    res: dict[str, str] = {}

    def rec(o):
        if isinstance(o, dict):
            p = o.get("path") or o.get("file") or o.get("name")
            if isinstance(p, str) and isinstance(o.get("sha256"), str):
                res[p.replace("\\", "/")] = o["sha256"]
            for k, v in o.items():
                if isinstance(v, dict) and isinstance(v.get("sha256"), str) and not any(x in v for x in ("path", "file", "name")):
                    res[str(k).replace("\\", "/")] = v["sha256"]
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(m)
    return res


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
    """Units of the frame per country and level. Geometry: computed (analysis) where the release has it, else display.
    Layout of the published release: adm1.parquet, adm2.parquet, analysis_<iso>_adm<n>.parquet in one folder."""

    def __init__(self, units: pd.DataFrame, froot: Path, strict: bool = True):
        self.units = units
        self.iso = dict(zip(units["unit_id"], units["iso3"]))
        self.parent = dict(zip(units["unit_id"], units["parent_id"]))
        self.name = dict(zip(units["unit_id"], units["name"]))
        self.level = dict(zip(units["unit_id"], units["level"]))
        self.adm0 = set(units.loc[units["level"] == "ADM0", "unit_id"])
        self.has = {1: set(units.loc[units["level"] == "ADM1", "iso3"]), 2: set(units.loc[units["level"] == "ADM2", "iso3"])}
        self.geometry_note: dict[int, dict[str, str]] = {1: {}, 2: {}}
        self.analysis_files: dict[int, dict[str, Path]] = {1: {}, 2: {}}
        self.display_files: dict[int, Path] = {}
        self.polys: dict[int, dict[str, gpd.GeoDataFrame]] = {1: {}, 2: {}}
        self.polys_display: dict[int, dict[str, gpd.GeoDataFrame]] = {1: {}, 2: {}}
        for f in sorted(froot.glob("analysis_*_adm*.parquet")):
            m = re.match(r"^analysis_([a-z]{3})_adm([12])\.parquet$", f.name)
            if m:
                self.analysis_files[int(m.group(2))][m.group(1).upper()] = f
        for lev in (1, 2):
            got = sorted(self.analysis_files[lev])
            if strict and got != EXPECTED_ANALYSIS[lev]:
                raise Stop(f"analysis files ADM{lev} of the frame: {got}; expected {EXPECTED_ANALYSIS[lev]}")
            self.display_files[lev] = froot / f"adm{lev}.parquet"
            disp = read_geo(self.display_files[lev])
            want = set(units.loc[units["level"] == f"ADM{lev}", "unit_id"])
            if set(disp["unit_id"]) != want:
                raise Stop(f"adm{lev}.parquet: unit_id set differs from units.csv ({len(set(disp['unit_id']) ^ want)} units)")
            use = disp
            for c, p in sorted(self.analysis_files[lev].items()):
                ids = set(units.loc[(units["level"] == f"ADM{lev}") & (units["iso3"] == c), "unit_id"])
                a = read_geo(p)
                extra = set(a["unit_id"]) - ids
                if extra:
                    raise Stop(f"{p.name}: {len(extra)} unit_id not in units.csv for {c}: {sorted(extra)[:5]}")
                left = sorted(ids - set(a["unit_id"]))          # units the computed file does not have keep the display geometry
                keep = disp[disp["unit_id"].isin(left)]
                use = pd.concat([use[~use["unit_id"].isin(ids)], a, keep], ignore_index=True)
                self.geometry_note[lev][c] = p.name + (f" ({len(left)} unit(s) from display: {', '.join(left)})" if left else "")
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
            stats[f"multi_hit_adm2:{c}"] += mm
        if c in polys[1]:
            a, b, mm = locate_in(lon[idx], lat[idx], polys[1][c])
            stats["multi_hit_adm1"] += mm
            stats[f"multi_hit_adm1:{c}"] += mm
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
    ap.add_argument("--aliases", default=None, help="atlas_adm1_aliases.csv (default <out-dir>\\rules\\atlas_adm1_aliases.csv, optional)")
    ap.add_argument("--prev-index", default=DEFAULT_PREV, help="folder data\\index of index 0.1.x (CSV files and build_hashes.json): regression check")
    ap.add_argument("--old-units", default=None, help="units.csv of abf-boundaries 0.2.0 (default <repo>\\data\\abf-boundaries\\v0.2.0\\units.csv, optional)")
    ap.add_argument("--no-sha-check", action="store_true", help="tests only")
    ap.add_argument("--no-count-check", action="store_true", help="tests only: skip the expected record counts")
    ap.add_argument("--no-regression", action="store_true", help="tests only: skip the comparison with index 0.1.x")
    a = ap.parse_args()
    repo, froot, rel = Path(a.repo), Path(a.frame_root), Path(a.release)
    out_dir = Path(a.out_dir) if a.out_dir else repo / "data" / "index"
    rules_p = Path(a.rules) if a.rules else out_dir / "rules" / "atlas_adm1_countries.csv"
    alias_p = Path(a.aliases) if a.aliases else out_dir / "rules" / "atlas_adm1_aliases.csv"
    prev_dir = Path(a.prev_index)
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
                 "units.csv": froot / "units.csv", "abf-boundaries manifest.json": froot / "manifest.json"}
        if rules_p.is_file():
            paths["atlas_adm1_countries.csv"] = rules_p
        if alias_p.is_file():
            paths["atlas_adm1_aliases.csv"] = alias_p
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
        ucount = units["level"].value_counts().to_dict()
        check("units.csv of the frame: ADM0 / ADM1 / ADM2", {k: ucount.get(k, 0) for k in EXPECTED_UNITS} == EXPECTED_UNITS or a.no_count_check,
              f"{ucount} (expected {EXPECTED_UNITS})")
        old_up = Path(a.old_units) if a.old_units else repo / "data" / "abf-boundaries" / "v0.2.0" / "units.csv"
        if old_up.is_file():
            ou = rcsv(old_up, ["unit_id", "iso3", "level", "name", "parent_id"])
            mm_ = ou.merge(units, on="unit_id", how="left", suffixes=("_o", "_n"))
            chg_ = {k: int((mm_[f"{k}_o"] != mm_[f"{k}_n"]).sum()) for k in ("iso3", "level", "name", "parent_id")}
            check("units of abf-boundaries 0.2.0 are unchanged in 0.3.0 (iso3, level, name, parent_id)", len(mm_) == len(ou) and not any(chg_.values()) and not mm_["iso3_n"].isna().any(),
                  f"{len(ou):,} old units; changed fields {chg_}; absent {int(mm_['iso3_n'].isna().sum())}")
            newu = units[~units["unit_id"].isin(ou["unit_id"])]
            check("new units are ADM1 of the 15 countries only", set(newu["level"]) == {"ADM1"} and sorted(set(newu["iso3"])) == sorted(NEW15) or a.no_count_check,
                  f"{len(newu)} new units, countries {sorted(set(newu['iso3']))}")
        else:
            log(f"  note: {old_up} not found, the check of old units is skipped")
        F = Frame(units, froot, strict=not a.no_count_check)
        check("countries with ADM1 / ADM2 in units.csv", True, f"{len(F.has[1])} / {sorted(F.has[2])}", hard=False)
        check("countries with ADM1 in units.csv", len(F.has[1]) == 123 or a.no_count_check, f"{len(F.has[1])} (expected 123)")
        for lev in (1, 2):
            for c, s in sorted(F.geometry_note[lev].items()):
                log(f"  ADM{lev} {c}: {s}")
        bgeom = {f"adm{lev}": {"default": f"adm{lev}.parquet", **{c: s for c, s in sorted(F.geometry_note[lev].items())}} for lev in (1, 2)}
        # the files the build reads against the manifest of the release
        frame_files = {"units.csv": froot / "units.csv", "adm1.parquet": F.display_files[1], "adm2.parquet": F.display_files[2]}
        for lev in (1, 2):
            for c, pth in sorted(F.analysis_files[lev].items()):
                frame_files[pth.name] = pth
        man_b = json.loads(paths["abf-boundaries manifest.json"].read_text(encoding="utf-8"))
        ent = manifest_entries(man_b)
        log(f"  manifest.json of the frame: {man_b.get('dataset')} {man_b.get('version')}, doi {man_b.get('doi')}, {len(ent)} files listed")
        check("manifest.json of the frame is abf-boundaries 0.3.0", man_b.get("dataset") == "abf-boundaries" and str(man_b.get("version")) == "0.3.0",
              f"{man_b.get('dataset')} {man_b.get('version')}")
        ffiles = {}
        for fn, pth in sorted(frame_files.items()):
            ffiles[fn] = sha_pair(pth)["sha256"]
            if a.no_sha_check:
                continue
            if fn in ent:
                check(f"sha256 of {fn} = manifest.json of the frame", ffiles[fn] == ent[fn], f"{ffiles[fn][:16]}...")
            else:
                check(f"{fn} is listed in manifest.json of the frame", False, "not listed: sha256 recorded only", hard=False)
        log(f"  frame files read: {len(ffiles)} (units.csv, 2 display, {len(F.analysis_files[1]) + len(F.analysis_files[2])} analysis); all sha256 recorded in build_hashes.json")

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
        if table:
            check("countries in the Atlas regions table (without USA)", len(table) == EXPECTED_TABLE_COUNTRIES or a.no_count_check,
                  f"{len(table)} (expected {EXPECTED_TABLE_COUNTRIES}); new in 0.2.0: {sorted(set(table) & set(NEW15))}")
        # ---- table of spellings (SPEC 0.2 r3 item 1.4): only the rows that were checked against the points and approved
        alias: dict[tuple[str, str], str] = {}
        alias_rows = []
        if alias_p.is_file():
            at = rcsv(alias_p, ["iso3", "adm1_raw", "unit_id", "reason", "decided_by"])
            for r in at.itertuples(index=False):
                k_ = (r.iso3, norm(r.adm1_raw))
                if not k_[1]:
                    raise Stop(f"atlas_adm1_aliases.csv: empty adm1_raw for {r.iso3}")
                if k_ in alias:
                    raise Stop(f"atlas_adm1_aliases.csv: duplicate row for {r.iso3} {r.adm1_raw!r}")
                if r.unit_id not in F.iso:
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} {r.adm1_raw!r}: unit_id {r.unit_id} is not in units.csv")
                if F.iso[r.unit_id] != r.iso3:
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} {r.adm1_raw!r}: unit {r.unit_id} belongs to {F.iso[r.unit_id]}")
                if r.iso3 not in table:
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} is not a country of atlas_adm1_countries.csv, its spelling row cannot be used")
                lvl_u = F.level[r.unit_id]
                if lvl_u not in ("ADM1", "ADM2") or (lvl_u == "ADM2" and table[r.iso3] != "adm1_or_adm2" and table[r.iso3] != "adm2") or \
                        (lvl_u == "ADM1" and table[r.iso3] == "adm2"):
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} {r.adm1_raw!r}: level {lvl_u} does not fit frame_level {table[r.iso3]}")
                if not r.reason.strip() or not r.decided_by.strip():
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} {r.adm1_raw!r}: reason and decided_by are required")
                if r.reason.split(":")[0] not in ("spelling", "former name", "merged", "within"):
                    raise Stop(f"atlas_adm1_aliases.csv: {r.iso3} {r.adm1_raw!r}: reason must start with spelling:, former name:, merged: or within:")
                alias[k_] = r.unit_id
                alias_rows.append(dict(iso3=r.iso3, adm1_raw=r.adm1_raw, unit_id=r.unit_id, reason=r.reason, decided_by=r.decided_by))
            check("rows of atlas_adm1_aliases.csv", len(alias) == EXPECTED_ALIAS_ROWS or a.no_count_check, f"{len(alias)} (expected {EXPECTED_ALIAS_ROWS}); countries {sorted({k[0] for k in alias})}")
            clash = [(k, v) for k, v in alias.items() if len(name_idx[(k[0], "ADM1")].get(k[1], [])) + len(name_idx[(k[0], "ADM2")].get(k[1], [])) > 0]
            log(f"  spelling rows whose written name already equals a unit name (they never fire, the name match goes first): {len(clash)} {clash[:5]}")
        else:
            log("  atlas_adm1_aliases.csv not found: the build runs without the table of spellings")

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
        alias_hit: Counter = Counter()                     # (iso3, normalised name) -> records placed through the table of spellings
        alias_recs: list[int] = []
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
                    if len(cand) != 1 and (c, key_) in alias:                       # the table of spellings: the name match goes first
                        cand = [alias[(c, key_)]]
                        clev = "adm2" if F.level[cand[0]] == "ADM2" else "adm1"
                        alias_hit[(c, key_)] += 1
                        alias_recs.append(i)
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
        R["how1"] = h1p
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

        # ---------------------------------------------------------------- spelling table: use and checks
        X: dict = {"alias_rows": alias_rows}
        a_hit = {f"{k[0]} {k[1]}": v for k, v in sorted(alias_hit.items())}
        unused = [r_ for r_ in alias_rows if alias_hit.get((r_["iso3"], norm(r_["adm1_raw"])), 0) == 0]
        check("every row of the table of spellings is used by at least one record", not unused, f"{len(unused)} unused: {[(r_['iso3'], r_['adm1_raw']) for r_ in unused[:5]]}", hard=False)
        arr_ = np.array(alias_recs, dtype=int)
        alias_old = [i for i in arr_ if adm0[i] not in NEW15]
        alias_new = [i for i in arr_ if adm0[i] in NEW15]
        log(f"  records placed through the table of spellings: {len(arr_)}; countries 0.1: {len(alias_old)}; the 15: {len(alias_new)}")
        X["alias_records"] = len(arr_)
        X["alias_old_ids"] = [str(rid[i]) for i in alias_old]
        X["alias_use"] = {k: int(v) for k, v in a_hit.items()}

        if a.no_regression:
            X["reg"] = None
            X["changed_old"] = []
            log("== regression skipped (--no-regression, tests only)")
        else:
            # ---------------------------------------------------------------- regression against index 0.1.x (SPEC 0.2 item 2.2)
            log("== regression against index 0.1.x")
            old_parts = []
            for s_ in SETS:
                d_ = prev_dir / s_
                if not d_.is_dir():
                    raise Stop(f"index 0.1.x not found: {d_} (give the folder with --prev-index)")
                for pth in sorted(d_.glob("*.csv")):
                    if pth.name in ("adm0_other.csv", "summary.csv"):
                        continue
                    old_parts.append(pd.read_csv(pth, dtype=str, keep_default_na=False, usecols=["record_id"] + CMP_COLS + ["boundary_release"]))
            O = pd.concat(old_parts, ignore_index=True)
            check("record_id of index 0.1.x = record_id of this build", len(O) == len(R) and set(O["record_id"]) == set(R["record_id"]), f"{len(O):,} old rows, {len(R):,} records")
            check("every row of index 0.1.x has boundary_release " + OLD_BOUNDARY_RELEASE, set(O["boundary_release"]) == {OLD_BOUNDARY_RELEASE}, str(sorted(set(O["boundary_release"]))))
            M = R[["record_id", "set"] + CMP_COLS + ["boundary_release"]].merge(O, on="record_id", how="inner", suffixes=("", "_old"))
            in15 = M["adm0"].isin(NEW15).to_numpy()
            any_diff = np.zeros(len(M), dtype=bool)
            for c_ in CMP_COLS:
                any_diff |= (M[c_] != M[c_ + "_old"]).to_numpy()
            a_ids = {str(rid[i]) for i in alias_old}
            D = M[any_diff & ~in15]
            log(f"  records outside the 15 countries that differ from 0.1.x in any of the nine fields: {len(D)}; changed by the table of spellings: {len(a_ids)}")
            check("outside the 15 countries only records of the table of spellings differ from 0.1.x (nine fields byte for byte otherwise)",
                  set(D["record_id"]) <= a_ids, f"{len(set(D['record_id']) - a_ids)} other record(s) differ: {sorted(set(D['record_id']) - a_ids)[:5]}")
            check("records changed by the table of spellings in the countries of 0.1 (BRA, FIN, FRA, JPN, MYS, NGA)",
                  len(D) == EXPECTED_ALIAS_CHANGED_OLD or a.no_count_check, f"{len(D)} (expected {EXPECTED_ALIAS_CHANGED_OLD}); by country {dict(Counter(D['adm0']))}")
            n15 = M[in15]
            for c_ in ("adm0", "adm0_basis", "adm0_other", "adm2", "adm1_point", "adm2_point"):
                check(f"the 15 countries: {c_} equals 0.1.x", bool((n15[c_] == n15[c_ + "_old"]).all()), f"{int((n15[c_] != n15[c_ + '_old']).sum())} differ")
            check("the 15 countries: adm1 was empty in 0.1.x (the frame had no ADM1 there)", bool((n15["adm1_old"] == "").all()), f"{int((n15['adm1_old'] != '').sum())} not empty")
            X["reg"] = dict(rows=len(M), old_diff_outside=len(D), rows15=len(n15), adm1_filled15=int(((n15["adm1_old"] == "") & (n15["adm1"] != "")).sum()),
                            note_tr={f"{o_!r} -> {n_!r}": int(v) for (o_, n_), v in Counter(zip(n15["unit_note_old"], n15["unit_note"])).most_common()},
                            basis_tr={f"{o_!r} -> {n_!r}": int(v) for (o_, n_), v in Counter(zip(n15["unit_basis_old"], n15["unit_basis"])).most_common()})
            X["changed_old"] = [dict(record_id=r_.record_id, adm0=r_.adm0, was=f"adm1={r_.adm1_old or '-'} adm2={r_.adm2_old or '-'} basis={r_.unit_basis_old or '-'} note={r_.unit_note_old or '-'}",
                                     now=f"adm1={r_.adm1 or '-'} adm2={r_.adm2 or '-'} basis={r_.unit_basis or '-'} note={r_.unit_note or '-'}") for r_ in D.sort_values("record_id").itertuples(index=False)]
            for e_ in X["changed_old"]:
                log(f"    changed: {e_['record_id']} {e_['adm0']}: {e_['was']} -> {e_['now']}")

        # Q5: computed geometry against display geometry (USA, NOR and the 15 national countries)
        diff = {}
        grp = {"USA, NOR": ["USA", "NOR"], "the 15 national countries": NEW15}
        dsp_c = set(NEW15) | {"USA", "NOR"}
        dpolys = {1: {c: g for c, g in F.polys_display[1].items() if c in dsp_c}, 2: {c: g for c, g in F.polys_display[2].items() if c in dsp_c}}
        d1, d2, _, _, _ = point_chain(lon, lat, adm0.astype(object), dpolys, F.parent, F.has, only=dsp_c)
        for gname, gl in grp.items():
            sel = (ub == "point") & np.isin(adm0, gl)
            for s_ in SETS:
                ms = sel & (R["set"].to_numpy() == s_)
                diff[(s_, gname)] = {"points": int(ms.sum()), "adm1_differs": int((a1[ms] != d1[ms]).sum()), "adm2_differs": int((a2[ms] != d2[ms]).sum())}
        log(f"  computed vs display geometry (rows placed by point): {diff}")
        X["multi"] = {k.split(":")[1]: int(v) for k, v in st.items() if k.startswith("multi_hit_adm1:") and v}
        X["multi2"] = {k.split(":")[1]: int(v) for k, v in st.items() if k.startswith("multi_hit_adm2:") and v}

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
                    "atlas_spelling_rows": len(alias_rows) if s_ == "abf-dc" else None, "frame_files_sha256": ffiles,
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
        if prev is not None and prev.get("index_version") != INDEX_VERSION:
            prev = None                                    # the file on disk is the build of another version (0.1.x): not a rerun
        same = None if prev is None else prev.get("files") == hashes
        ohp = prev_dir / "build_hashes.json"
        if ohp.is_file():
            ofiles = set(json.loads(ohp.read_text(encoding="utf-8")).get("files", {}))
            X["files_new"], X["files_gone"] = sorted(set(hashes) - ofiles), sorted(ofiles - set(hashes))
            log(f"  output files against 0.1.x: new {len(X['files_new'])} {X['files_new'][:6]}, missing {len(X['files_gone'])} {X['files_gone'][:6]}")
            check("list of output files against index 0.1.x (new and missing)", not X["files_new"] and not X["files_gone"],
                  f"new {len(X['files_new'])}, missing {len(X['files_gone'])}", hard=False)
        else:
            X["files_new"], X["files_gone"] = None, None
            log(f"  {ohp} not found: the list of output files is not compared with 0.1.x")
        X["frame_files"] = ffiles
        report = make_report(a, inputs, checks, R, per_set, fsize, hashes, diff, dis, table, F, same, time.time() - t0, X)
        out_dir.mkdir(parents=True, exist_ok=True)
        for k, v in files.items():
            p = out_dir / k
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(v)
        (out_dir / "build_report.md").write_bytes(report.encode("utf-8"))
        hpath.write_bytes((json.dumps({"index_version": INDEX_VERSION, "boundary_release": BOUNDARY_RELEASE,
                                       "inputs": {k: {kk: vv for kk, vv in v.items() if kk != "path"} for k, v in sorted(inputs.items())},
                                       "frame_files_sha256": ffiles, "files": hashes}, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        log(f"== done in {time.time() - t0:.0f} s; rerun identical to the previous build: {same}; {len(files)} files in {out_dir}")
        return 0
    except Stop as e:
        log("")
        log(f"STOP: {e}")
        log("Nothing was written.")
        return 1


def make_report(a, inputs, checks, R, per_set, fsize, hashes, diff, dis, table, F, same, secs, X) -> str:
    L = ["# abf-index 0.2.0 · build report", "", f"Index version {INDEX_VERSION}; frame {BOUNDARY_RELEASE}; rules: SPEC_INDEX_territory_v0_1 r11 and SPEC_INDEX_territory_v0_2 r3.", "",
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
    # ---- the 15 national countries
    L += ["## The 15 countries with new ADM1 (COL, EST, HKG, IDN, IRL, KOR, LUX, LVA, MEX, NZL, PER, PHL, THA, TWN, VNM)", "",
          "adm1 by the Atlas field (table countries), by the point strictly within a unit, by the nearest unit within 22.2 km, no_unit_near, no_point, region_not_matched.", "",
          "| Set | Country | records | with point | adm1 filled | by field | by point: within | by point: nearest | no_unit_near | no_point | region_not_matched | points in two units |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tot = defaultdict(lambda: defaultdict(int))
    for s_ in SETS:
        for c in NEW15:
            g = R[(R["set"] == s_) & (R["adm0"] == c)]
            if not len(g):
                continue
            bp = g[g["unit_basis"] == "point"]
            row = dict(records=len(g), with_point=int(g["lon"].notna().sum()), filled=int((g["adm1"] != "").sum()), field=int((g["unit_basis"] == "field").sum()),
                       within=int((bp["how1"] == "within").sum()), near=int((bp["how1"] == "near").sum()), nun=int((g["unit_note"] == "no_unit_near").sum()),
                       nop=int((g["unit_note"] == "no_point").sum()), rnm=int((g["unit_note"] == "region_not_matched").sum()),
                       multi=int(X["multi"].get(c, 0)) if s_ == "abf-dc" else 0)
            for k_, v_ in row.items():
                tot[s_][k_] += v_
            L.append(f"| {s_} | {c} | {row['records']:,} | {row['with_point']:,} | {row['filled']:,} | {row['field']:,} | {row['within']:,} | {row['near']:,} | {row['nun']:,} | {row['nop']:,} | {row['rnm']:,} | {row['multi'] if s_ == 'abf-dc' else '(see abf-dc)'} |")
    L += ["", "| Set | records | adm1 filled | by field | by point: within | by point: nearest | no_unit_near | no_point | region_not_matched |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s_ in SETS:
        t_ = tot[s_]
        L.append(f"| {s_} | {t_['records']:,} | {t_['filled']:,} | {t_['field']:,} | {t_['within']:,} | {t_['near']:,} | {t_['nun']:,} | {t_['nop']:,} | {t_['rnm']:,} |")
    L += ["", f"Points in two units of one country (lowest unit_id taken), the 15 countries, counted once per distinct point over all sets (lookups of the set records): {dict(X['multi'])}.", ""]
    # ---- spelling table
    L += ["## Table of spellings (atlas_adm1_aliases.csv)", "", f"{len(X['alias_rows'])} rows; records placed through it: {X['alias_records']}.", "",
          "| iso3 | adm1_raw | unit_id | records | reason | decided_by |", "|---|---|---|---:|---|---|"]
    for r_ in X["alias_rows"]:
        L.append(f"| {r_['iso3']} | {r_['adm1_raw']} | {r_['unit_id']} | {X['alias_use'].get(r_['iso3'] + ' ' + norm(r_['adm1_raw']), 0)} | {r_['reason'].replace('|', '/')} | {r_['decided_by']} |")
    # ---- regression
    rg = X["reg"]
    if rg is None:
        L += ["", "## Regression against index 0.1.x", "", "Skipped (--no-regression, tests only).", ""]
    else:
      L += ["", "## Regression against index 0.1.x", "",
          f"Records compared: {rg['rows']:,}. Nine fields (adm0, adm0_basis, adm0_other, adm1, adm2, unit_basis, unit_note, adm1_point, adm2_point):", "",
          f"- outside the 15 countries: {rg['old_diff_outside']} records differ, all through the table of spellings (expected {EXPECTED_ALIAS_CHANGED_OLD}): BRA, FIN, FRA, JPN, MYS, NGA;",
          f"- the 15 countries ({rg['rows15']:,} records): adm0, adm0_basis, adm0_other, adm2, adm1_point, adm2_point equal 0.1.x; adm1 filled {rg['adm1_filled15']:,} (empty in 0.1.x);",
          f"- unit_note transitions in the 15 (old -> new): {rg['note_tr']};", f"- unit_basis transitions in the 15 (old -> new): {rg['basis_tr']}.", "",
          f"`boundary_release` changes from {OLD_BOUNDARY_RELEASE} to {BOUNDARY_RELEASE} in all rows.", "",
          "Records of the countries of 0.1 changed by the table of spellings (list):", "", "| record_id | adm0 | 0.1.x | 0.2.0 |", "|---|---|---|---|"]
    for e_ in X["changed_old"]:
        L.append(f"| {e_['record_id']} | {e_['adm0']} | {e_['was']} | {e_['now']} |")
    if X.get("files_new") is not None:
        L += ["", f"Output files against index 0.1.x: new {len(X['files_new'])} {X['files_new'][:10]}; missing {len(X['files_gone'])} {X['files_gone'][:10]}."]
    L += ["", "## Frame files read (sha256)", "", "| File | sha256 |", "|---|---|"]
    for k_, h_ in sorted(X["frame_files"].items()):
        L.append(f"| {k_} | `{h_}` |")
    L += [""]
    L += ["## Rows with adm1_point (Atlas: adm0 by the field, point in another country)", "", "| record_id | adm0 | adm0_other | adm1_point | adm2_point |", "|---|---|---|---|---|"]
    for r in R[R["adm1_point"] != ""].itertuples(index=False):
        L.append(f"| {r.record_id} | {r.adm0} | {r.adm0_other} | {r.adm1_point} | {r.adm2_point} |")
    L += ["", "## Geometry: computed against display", "", "Rows placed by point whose unit differs between the computed and the display geometry:", "",
          "| Group | Set | rows by point | adm1 differs | adm2 differs |", "|---|---|---:|---:|---:|"]
    for (s_, g_), d in diff.items():
        L.append(f"| {g_} | {s_} | {d['points']:,} | {d['adm1_differs']:,} | {d['adm2_differs']:,} |")
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
