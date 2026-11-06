r"""abf-energy / abf-energync: build the GEM power plant layers (SPEC_GEM_plants_v0_1_0 r4, section 2).

Reads ONE input (the GEM Global Integrated Power Tracker xlsx, September 2026) and the abf-boundaries v0.2.0 frame
(adm0.parquet, contested_areas.parquet). Writes into data\gem\ :
    energy_plants_gem_units.csv            abf-energy,   one row per GEM unit/phase ID (not TransitionZero)
    energy_plants_gem_locations.csv        abf-energy,   places (map layer)
    energy_plants_gem_tzsam_units.csv      abf-energync, one row per GEM unit/phase ID (TransitionZero ids)
    energy_plants_gem_tzsam_locations.csv  abf-energync, places (map layer)
    rules\gem_status_groups.csv, rules\gem_iso3_to_adm0.csv, rules\gem_country_table.csv
    build_report.md, build_hashes.json
Extra lists for the research chats go to research\gem\ (not in git).

Run (from the repository root, cmd):
    python scripts\gem\build_gem_layers.py

Read-only for the input. Same input + same frame + same rule tables => byte-identical CSV (P5): no times, no random order.
Any failed check stops the build BEFORE the CSV files are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

LOG = logging.getLogger("gem_build")

# ------------------------------------------------------------------ constants from SPEC r4
EXPECTED_SHA256 = "34749042643b15cac4423ae67864ad36c391013aa2d5acc65ae7492c5e33ee27"
EXPECTED_ROWS = 183404
EXPECTED_TZ = 18732
EXPECTED_NONTZ = 164672
EXPECTED_MW_TOTAL = 22641664
EXPECTED_MW_TZ = 84304
EXPECTED_CAPTIVE = (399, 227213)     # blocks, MW (rounded)
EXPECTED_PPA = (32, 11404)
EXPECTED_APPROX = 73694
TZ_RE = re.compile(r"(?<![A-Za-z])TZ\s*:")
GROUP_KM = 1000.0                    # section 2.6 item 1
NEAREST_M = 22200.0                  # section 2.4 item 3: 12 nautical miles

DEFAULT_GIPT = r"D:\GISData\Energy\GEM\Global Integrated Power September 2026 V2.xlsx"
DEFAULT_FRAME = r"D:\GISData\Boundaries\out\abf-boundaries-v0.2.0\display"
SHEET_DATA = "Power facilities"
SHEET_COUNTRIES = "Regions, area, and countries"

# source column -> field (names copied from the file, GEM_preflight.txt section 1c)
SRC = {
    "record_id": "GEM unit/phase ID", "location_id": "GEM location ID", "plant_name": "Plant / Project name",
    "unit_name": "Unit / Phase name", "type": "Type", "technology": "Technology", "fuel": "Fuel (combustion only)",
    "capacity_mw": "Capacity (MW)", "capacity_rating": "Capacity rating (solar only)", "status": "Status",
    "start_year": "Start year", "retired_year": "Retired year", "owners": "Owner(s)", "operators": "Operator(s)",
    "country_area": "Country/area", "subnational_unit": "Subnational unit (state, province)",
    "location_accuracy": "Location accuracy", "lon": "Longitude", "lat": "Latitude",
    "captive_industry_type": "Captive Industry Type", "data_center_ppa": "Data Center PPA",
    "river": "River / Watercourse (hydropower only)", "other_ids_location": "Other IDs (location)",
    "other_ids_unit": "Other IDs (unit/phase)", "wiki_url": "GEM.Wiki URL",
}

STATUS_GROUPS_DEFAULT = [
    ("announced", "announced", "Announced"), ("pre-construction", "pre_construction", "Pre-construction"),
    ("construction", "construction", "Construction"), ("operating", "operating", "Operating"),
    ("shelved", "shelved", "Shelved"), ("shelved - inferred 2 y", "shelved", "Shelved"),
    ("cancelled", "cancelled", "Cancelled"), ("cancelled - inferred 4 y", "cancelled", "Cancelled"),
    ("mothballed", "mothballed", "Mothballed"), ("retired", "retired", "Retired"),
]

UNIT_COLS = ["record_id", "location_id", "plant_name", "unit_name", "type", "technology", "fuel", "capacity_mw",
             "capacity_rating", "capacity_class", "status", "status_group", "start_year", "retired_year", "owners",
             "operators", "country_area", "subnational_unit", "iso3_gem", "iso3_source", "iso3_frame", "iso3_frame_rule",
             "control_iso3", "location_accuracy", "coord_precision", "coord_source", "lon", "lat",
             "captive_industry_type", "data_center_ppa", "dc_link", "river", "other_ids_location", "other_ids_unit",
             "wiki_url"]
PLACE_COLS = ["record_id", "location_id", "plant_name", "wiki_url", "type", "status_group", "statuses", "technologies",
              "capacity_mw", "capacity_class", "n_units", "capacity_ratings", "start_year_min", "start_year_max",
              "iso3_gem", "iso3_source", "iso3_frame", "iso3_frame_rule", "control_iso3", "subnational_unit",
              "location_accuracy", "coord_precision", "coord_source", "lon", "lat", "n_units_dc_link", "dc_links",
              "n_units_other_set"]


class Stop(Exception):
    """A stop condition of the SPEC: the build must not continue."""


# ------------------------------------------------------------------ helpers
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fmt_num(v) -> str:
    """Number -> shortest text; integer-valued -> no '.0'. Text stays as it is."""
    if v is None:
        return ""
    if isinstance(v, bool):
        raise Stop(f"boolean cell {v!r} where a number or text is expected")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return str(int(v)) if v == int(v) and abs(v) < 1e15 else repr(v)
    return str(v)


def to_float(v, what: str) -> float:
    if isinstance(v, bool) or v is None:
        raise Stop(f"{what}: empty or boolean value")
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        raise Stop(f"{what}: not a number: {v!r}")


def capacity_class(mw: float) -> str:
    if mw < 10:
        return "lt10"
    if mw < 100:
        return "10_99"
    if mw < 1000:
        return "100_999"
    return "ge1000"


def type_code(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


# ------------------------------------------------------------------ 1. read the workbook
def read_gipt(path: Path):
    import openpyxl
    LOG.info("Reading workbook (several minutes) ...")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = wb.sheetnames
    for need in (SHEET_DATA, SHEET_COUNTRIES):
        if need not in names:
            raise Stop(f"sheet {need!r} not found; sheets: {names}")
    # data sheet
    ws = wb[SHEET_DATA]
    it = ws.iter_rows(values_only=True)
    header = [("" if c is None else str(c).strip()) for c in next(it)]
    missing = [v for v in SRC.values() if v not in header]
    if missing:
        raise Stop(f"columns not in the file (names are copied from the pre-flight, nothing is guessed): {missing}")
    idx = {k: header.index(v) for k, v in SRC.items()}
    rows = []
    for n, r in enumerate(it, start=2):
        if r is None or all(c is None for c in r):
            continue
        rows.append({k: r[i] for k, i in idx.items()})
        if len(rows) % 40000 == 0:
            LOG.info("  %d rows", len(rows))
    # country reference sheet
    ws2 = wb[SHEET_COUNTRIES]
    it2 = ws2.iter_rows(values_only=True)
    h2 = [("" if c is None else str(c).strip()) for c in next(it2)]
    name_cols = [c for c in h2 if c.startswith("GEM Standard Country Name")]
    if len(name_cols) != 1 or "ISO-alpha3 Code" not in h2:
        raise Stop(f"country sheet: need one 'GEM Standard Country Name…' column and 'ISO-alpha3 Code'; header: {h2}")
    ni, ii = h2.index(name_cols[0]), h2.index("ISO-alpha3 Code")
    ctab = []
    for r in it2:
        if r is None or r[ni] is None:
            continue
        ctab.append((str(r[ni]).strip(), "" if r[ii] is None else str(r[ii]).strip()))
    wb.close()
    return rows, ctab, name_cols[0]


# ------------------------------------------------------------------ 2. frame
class Frame:
    def __init__(self, fdir: Path):
        import geopandas as gpd
        self.gpd = gpd
        p0, pc = fdir / "adm0.parquet", fdir / "contested_areas.parquet"
        for p in (p0, pc):
            if not p.exists():
                raise Stop(f"frame file not found: {p} (pass --frame-dir)")
        a = gpd.read_parquet(p0)
        iso = "iso3" if "iso3" in a.columns else ("ISO3" if "ISO3" in a.columns else None)
        if iso is None:
            raise Stop(f"adm0.parquet has no iso3 column; columns: {list(a.columns)}")
        a = a.rename(columns={iso: "iso3"})[["iso3", "geometry"]]
        if a.crs is not None and a.crs.to_epsg() != 4326:
            a = a.to_crs(4326)
        self.adm0 = a.reset_index(drop=True)
        z = gpd.read_parquet(pc)
        for c in ("controlled_by", "area_id"):
            if c not in z.columns:
                raise Stop(f"contested_areas.parquet: column {c!r} missing; columns: {list(z.columns)}")
        if z.crs is not None and z.crs.to_epsg() != 4326:
            z = z.to_crs(4326)
        self.zones = z[["area_id", "controlled_by", "geometry"]].sort_values("area_id").reset_index(drop=True)
        self.iso_set = set(self.adm0["iso3"])
        self.p0_sha, self.pc_sha = sha256_file(p0), sha256_file(pc)

    def assign(self, coords: list, prefer: dict):
        """coords: unique (lon, lat). prefer: coord -> iso3_gem. -> {coord: (iso3_frame, rule, control_iso3)}."""
        gpd = self.gpd
        from pyproj import Geod
        from shapely.geometry import Point
        from shapely.ops import nearest_points
        geod = Geod(ellps="WGS84")
        pts = gpd.GeoDataFrame({"k": range(len(coords))}, geometry=gpd.points_from_xy([c[0] for c in coords], [c[1] for c in coords]),
                               crs="EPSG:4326")
        j = gpd.sjoin(pts, self.adm0, how="left", predicate="within")
        found: dict = {}
        n_overlap = 0
        for k, grp in j.groupby("k"):
            isos = sorted(set(grp["iso3"].dropna()))
            if isos:
                if len(isos) > 1:
                    n_overlap += 1
                pref = prefer.get(coords[k])
                found[k] = (pref if pref in isos else isos[0], "within")
        miss = [k for k in range(len(coords)) if k not in found]
        LOG.info("frame: %d unique points, %d inside ADM0, %d outside, %d overlaps", len(coords), len(found), len(miss), n_overlap)
        geoms = list(self.adm0.geometry)
        isos_all = list(self.adm0["iso3"])
        sidx = self.adm0.sindex
        for k in miss:
            lon, lat = coords[k]
            p = Point(lon, lat)
            best = None
            for gi in sidx.query(p.buffer(1.5)):
                q = nearest_points(p, geoms[gi])[1]
                d = geod.inv(lon, lat, q.x, q.y)[2]
                cand = (d, isos_all[gi])
                if best is None or cand < best:
                    best = cand
            if best is not None and best[0] <= NEAREST_M:
                found[k] = (best[1], "nearest_12nmi")
            else:
                found[k] = ("", "")
        ctl: dict = {}
        n_multi = 0
        zj = gpd.sjoin(pts, self.zones, how="left", predicate="within") if len(self.zones) else pts.assign(area_id=None, controlled_by=None)
        for k, grp in zj.sort_values("area_id").groupby("k"):
            vals = [v for v in grp["controlled_by"].dropna()]
            if len(set(vals)) > 1:
                n_multi += 1
            ctl[k] = vals[0] if vals else ""
        if n_multi:
            LOG.warning("%d points lie in zones with different controlled_by; first by area_id is used", n_multi)
        return {coords[k]: (found[k][0], found[k][1], ctl.get(k, "")) for k in range(len(coords))}, n_overlap, n_multi


# ------------------------------------------------------------------ 3. build
def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gipt", default=DEFAULT_GIPT)
    ap.add_argument("--frame-dir", default=DEFAULT_FRAME)
    ap.add_argument("--out-dir", default=str(root / "data" / "gem"))
    ap.add_argument("--research-dir", default=str(root / "research" / "gem"))
    ap.add_argument("--no-sha-check", action="store_true", help="tests only")
    ap.add_argument("--no-count-check", action="store_true", help="tests only: skip the expected row/MW counts")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    out_dir, res_dir, gipt = Path(args.out_dir), Path(args.research_dir), Path(args.gipt)
    rules_dir = out_dir / "rules"
    t0 = time.time()
    report: list = []
    fails: list = []

    def check(name: str, ok: bool, detail: str):
        report.append(f"| {name} | {'OK' if ok else '**FAIL**'} | {detail} |")
        if not ok:
            fails.append(f"{name}: {detail}")
        LOG.info("check %s: %s (%s)", name, "OK" if ok else "FAIL", detail)

    try:
        # --- input
        if not gipt.exists():
            raise Stop(f"input not found: {gipt}")
        sha_in = sha256_file(gipt)
        if not args.no_sha_check and sha_in != EXPECTED_SHA256:
            raise Stop(f"input SHA-256 {sha_in} != expected {EXPECTED_SHA256}")
        rows, ctab, cname_col = read_gipt(gipt)
        LOG.info("rows: %d", len(rows))

        # --- rule tables
        sg_path = rules_dir / "gem_status_groups.csv"
        if not sg_path.exists():
            write_csv(pd.DataFrame(STATUS_GROUPS_DEFAULT, columns=["status", "status_group", "label"]), sg_path)
        sg = pd.read_csv(sg_path, dtype=str, keep_default_na=False)
        if list(sg.columns) != ["status", "status_group", "label"]:
            raise Stop(f"{sg_path}: columns must be status,status_group,label; got {list(sg.columns)}")
        status_group = dict(zip(sg["status"], sg["status_group"]))
        group_label = dict(zip(sg["status_group"], sg["label"]))

        # --- country table (2.4 item 1)
        by_name: dict = {}
        for nm, iso in ctab:
            if nm in by_name and by_name[nm] != iso:
                raise Stop(f"country sheet: name {nm!r} appears twice with different ISO3")
            by_name[nm] = iso

        # --- blocks
        seen_ids: set = set()
        blocks: list = []
        for r in rows:
            b = {k: ("" if r[k] is None else r[k]) for k in SRC}
            rid = str(b["record_id"]).strip()
            if not rid:
                raise Stop("empty GEM unit/phase ID")
            if rid in seen_ids:
                raise Stop(f"duplicate GEM unit/phase ID {rid}")
            seen_ids.add(rid)
            b["record_id"] = rid
            for k in ("location_id", "plant_name", "type", "status", "country_area", "wiki_url"):
                b[k] = str(b[k]) if b[k] != "" else ""
                if k != "plant_name":
                    b[k] = b[k].strip()
                if not b[k].strip():
                    raise Stop(f"{rid}: empty {SRC[k]}")
            b["unit_name"] = fmt_num(b["unit_name"])
            for k in ("technology", "fuel", "capacity_rating", "owners", "operators", "subnational_unit", "captive_industry_type",
                      "data_center_ppa", "river", "other_ids_location", "other_ids_unit"):
                b[k] = "" if b[k] == "" else str(b[k])
            for k in ("start_year", "retired_year"):
                b[k] = fmt_num(b[k]) if b[k] != "" else ""
            if b["status"] not in status_group:
                raise Stop(f"{rid}: status {b['status']!r} is not in {sg_path.name}")
            b["status_group"] = status_group[b["status"]]
            mw = to_float(b["capacity_mw"], f"{rid} capacity")
            b["_mw"] = mw
            b["capacity_mw"] = fmt_num(mw)
            b["capacity_class"] = capacity_class(mw)
            lon, lat = to_float(b["lon"], f"{rid} longitude"), to_float(b["lat"], f"{rid} latitude")
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise Stop(f"{rid}: coordinates out of range {lon},{lat}")
            b["_xy"] = (lon, lat)
            b["lon"], b["lat"] = fmt_num(lon), fmt_num(lat)
            acc = str(b["location_accuracy"]).strip().lower()
            if acc not in ("exact", "approximate"):
                raise Stop(f"{rid}: location accuracy {b['location_accuracy']!r}")
            b["location_accuracy"] = acc
            b["coord_precision"] = "site" if acc == "exact" else "approximate"
            b["coord_source"] = "gem"
            ppa = str(b["data_center_ppa"]).strip().lower() == "yes"
            cap = "data center" in str(b["captive_industry_type"]).lower()
            b["dc_link"] = ";".join([c for c, f in (("captive_dc", cap), ("dc_ppa", ppa)) if f])
            iso = by_name.get(b["country_area"])
            if iso is None or not iso:
                raise Stop(f"{rid}: Country/area {b['country_area']!r} has no ISO3 in the sheet {SHEET_COUNTRIES!r}")
            b["iso3_gem"] = iso
            b["_tz"] = bool(TZ_RE.search(b["other_ids_unit"]))
            blocks.append(b)
        n_tz = sum(1 for b in blocks if b["_tz"])
        check("rows in the sheet", args.no_count_check or len(blocks) == EXPECTED_ROWS, f"{len(blocks):,} (expected {EXPECTED_ROWS:,})")
        check("TransitionZero records", args.no_count_check or n_tz == EXPECTED_TZ, f"{n_tz:,} (expected {EXPECTED_TZ:,}); rule {TZ_RE.pattern}")
        check("non-TZ records", args.no_count_check or len(blocks) - n_tz == EXPECTED_NONTZ, f"{len(blocks) - n_tz:,} (expected {EXPECTED_NONTZ:,})")

        # --- frame (2.4 items 2-4)
        frame = Frame(Path(args.frame_dir))
        coords = sorted({b["_xy"] for b in blocks})
        prefer = {}
        for b in blocks:
            prefer.setdefault(b["_xy"], b["iso3_gem"])
        fmap, n_overlap, n_multi = frame.assign(coords, prefer)
        for b in blocks:
            b["iso3_frame"], b["iso3_frame_rule"], b["control_iso3"] = fmap[b["_xy"]]

        # iso3_source
        map_path = rules_dir / "gem_iso3_to_adm0.csv"
        manual: dict = {}
        if map_path.exists():
            for r in pd.read_csv(map_path, dtype=str, keep_default_na=False).to_dict("records"):
                if not r["reason"].startswith("part of "):
                    manual[r["iso3_gem"]] = r
        need = sorted({b["iso3_gem"] for b in blocks} - frame.iso_set)
        auto_rows, unresolved = [], []
        for iso in need:
            if iso in manual:
                tgt = manual[iso]["iso3_source"]
                if tgt not in frame.iso_set:
                    raise Stop(f"{map_path.name}: {iso} -> {tgt} is not an ADM0 unit")
                continue
            grp = [b for b in blocks if b["iso3_gem"] == iso]
            frames = {b["iso3_frame"] for b in grp}
            in_zone = [b for b in grp if b["control_iso3"]]
            if len(frames) == 1 and "" not in frames and not in_zone:
                tgt = next(iter(frames))
                auto_rows.append({"iso3_gem": iso, "iso3_source": tgt, "reason": f"part of {tgt} in the abf-boundaries frame"})
            else:
                unresolved.append((iso, grp))
        map_rows = sorted(auto_rows + list(manual.values()), key=lambda r: r["iso3_gem"])
        write_csv(pd.DataFrame(map_rows, columns=["iso3_gem", "iso3_source", "reason"]), map_path)
        if unresolved:
            res_dir.mkdir(parents=True, exist_ok=True)
            lines = ["iso3_gem,record_id,country_area,lon,lat,iso3_frame,iso3_frame_rule,control_iso3"]
            for iso, grp in unresolved:
                for b in grp:
                    lines.append(",".join(csv_cell(x) for x in (iso, b["record_id"], b["country_area"], b["lon"], b["lat"],
                                                                b["iso3_frame"], b["iso3_frame_rule"], b["control_iso3"])))
            (res_dir / "iso3_unresolved.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            raise Stop("iso3_gem not in ADM0 and the points are not all in one unit (or outside / in a contested zone): "
                       f"{[u[0] for u in unresolved]}. List: {res_dir / 'iso3_unresolved.csv'}. Ask [RES]7 for rows of "
                       f"{map_path.name}, then run again.")
        src_map = {r["iso3_gem"]: r["iso3_source"] for r in map_rows}
        for b in blocks:
            b["iso3_source"] = b["iso3_gem"] if b["iso3_gem"] in frame.iso_set else src_map[b["iso3_gem"]]

        # --- sets
        sets = {"abf-energy": [b for b in blocks if not b["_tz"]], "abf-energync": [b for b in blocks if b["_tz"]]}
        loc_count = {k: Counter(b["location_id"] for b in v) for k, v in sets.items()}
        names = {"abf-energy": ("energy_plants_gem_units", "energy_plants_gem_locations"),
                 "abf-energync": ("energy_plants_gem_tzsam_units", "energy_plants_gem_tzsam_locations")}
        units_df: dict = {}
        places_df: dict = {}
        wide_rows: list = []
        split_rows: list = []
        place_stats: dict = {}
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        for ds, bl in sets.items():
            other = "abf-energync" if ds == "abf-energy" else "abf-energy"
            bl.sort(key=lambda b: b["record_id"])
            units_df[ds] = pd.DataFrame([{c: b[c] for c in UNIT_COLS} for b in bl], columns=UNIT_COLS, dtype=object)
            byloc = defaultdict(list)
            for b in bl:
                byloc[b["location_id"]].append(b)
            places, n_split = [], 0
            for loc in sorted(byloc):
                lb = byloc[loc]
                for fld in ("plant_name", "wiki_url"):
                    if len({b[fld] for b in lb}) != 1:
                        raise Stop(f"location {loc}: {fld} differs between blocks")
                xs = [b["_xy"][0] for b in lb]
                ys = [b["_xy"][1] for b in lb]
                if max(xs) - min(xs) > 1 or max(ys) - min(ys) > 1:
                    wide_rows.append((ds, loc, lb[0]["plant_name"], lb[0]["country_area"], len(lb), round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)))
                anchors: list = []          # (block, xy)
                gid: dict = {}
                for b in lb:
                    placed = None
                    for g, a in enumerate(anchors):
                        if a["_xy"] == b["_xy"] or geod.inv(a["_xy"][0], a["_xy"][1], b["_xy"][0], b["_xy"][1])[2] <= GROUP_KM:
                            placed = g
                            break
                    if placed is None:
                        anchors.append(b)
                        placed = len(anchors) - 1
                    gid[b["record_id"]] = placed
                multi = len(anchors) > 1
                if multi:
                    n_split += 1
                    split_rows.append((ds, loc, lb[0]["plant_name"], len(lb), len(anchors)))
                key: dict = defaultdict(list)
                for b in lb:
                    key[(gid[b["record_id"]], b["type"], b["status_group"])].append(b)
                for (g, tp, sgp), mem in sorted(key.items(), key=lambda kv: (kv[0][0], type_code(kv[0][1]), kv[0][2])):
                    a = anchors[g]
                    rid = f"{loc}-{type_code(tp)}-{sgp}" + (f"-p{g + 1}" if multi else "")
                    mw = round(math.fsum(m["_mw"] for m in mem), 6)
                    years = [int(m["start_year"]) for m in mem if re.fullmatch(r"\d{4}", m["start_year"])]
                    dcs = sorted({c for m in mem for c in m["dc_link"].split(";") if c})
                    places.append({
                        "record_id": rid, "location_id": loc, "plant_name": a["plant_name"], "wiki_url": a["wiki_url"], "type": tp,
                        "status_group": sgp, "statuses": "; ".join(sorted({m["status"] for m in mem})),
                        "technologies": "; ".join(sorted({m["technology"] for m in mem if m["technology"]})),
                        "capacity_mw": fmt_num(mw), "capacity_class": capacity_class(mw), "n_units": str(len(mem)),
                        "capacity_ratings": "; ".join(sorted({m["capacity_rating"] for m in mem if m["capacity_rating"]})),
                        "start_year_min": str(min(years)) if years else "", "start_year_max": str(max(years)) if years else "",
                        "iso3_gem": a["iso3_gem"], "iso3_source": a["iso3_source"], "iso3_frame": a["iso3_frame"],
                        "iso3_frame_rule": a["iso3_frame_rule"], "control_iso3": a["control_iso3"],
                        "subnational_unit": "; ".join(sorted({m["subnational_unit"] for m in mem if m["subnational_unit"]})),
                        "location_accuracy": a["location_accuracy"], "coord_precision": a["coord_precision"], "coord_source": "gem",
                        "lon": a["lon"], "lat": a["lat"], "n_units_dc_link": str(sum(1 for m in mem if m["dc_link"])),
                        "dc_links": "; ".join(dcs), "n_units_other_set": str(loc_count[other].get(loc, 0)),
                        "_mw": mw, "_n": len(mem),
                    })
            places.sort(key=lambda p: p["record_id"])
            places_df[ds] = pd.DataFrame([{c: p[c] for c in PLACE_COLS} for p in places], columns=PLACE_COLS, dtype=object)
            place_stats[ds] = dict(places=places, n_split=n_split, n_locations=len(byloc))

        # --- checks 2.7
        tot_mw = math.fsum(b["_mw"] for b in blocks)
        tz_mw = math.fsum(b["_mw"] for b in sets["abf-energync"])
        check("blocks in both sets", len(sets["abf-energy"]) + len(sets["abf-energync"]) == len(blocks), f"{len(sets['abf-energy']):,} + {len(sets['abf-energync']):,} = {len(blocks):,}")
        check("capacity, both sets", args.no_count_check or round(tot_mw) == EXPECTED_MW_TOTAL, f"{tot_mw:,.1f} MW (expected {EXPECTED_MW_TOTAL:,})")
        check("capacity, TZ set", args.no_count_check or round(tz_mw) == EXPECTED_MW_TZ, f"{tz_mw:,.1f} MW (expected {EXPECTED_MW_TZ:,})")
        for ds, bl in sets.items():
            ps = place_stats[ds]["places"]
            check(f"{ds}: record_id unique", len({p['record_id'] for p in ps}) == len(ps), f"{len(ps):,} places")
            check(f"{ds}: sum of n_units", sum(p["_n"] for p in ps) == len(bl), f"{sum(p['_n'] for p in ps):,} = {len(bl):,} blocks")
            a, bsum = defaultdict(float), defaultdict(float)
            for b in bl:
                a[(b["type"], b["status_group"])] += b["_mw"]
            for p in ps:
                bsum[(p["type"], p["status_group"])] += p["_mw"]
            bad = [k for k in set(a) | set(bsum) if abs(a.get(k, 0) - bsum.get(k, 0)) > 1e-3]
            check(f"{ds}: MW by type x status_group, places = blocks", not bad, f"{len(set(a) | set(bsum))} cells" + (f"; differ: {bad[:5]}" if bad else ""))
        cap_blocks = [b for b in blocks if "captive_dc" in b["dc_link"]]
        ppa_blocks = [b for b in blocks if "dc_ppa" in b["dc_link"]]
        both = [b for b in blocks if ";" in b["dc_link"]]
        check("captive_dc", args.no_count_check or (len(cap_blocks), round(math.fsum(b['_mw'] for b in cap_blocks))) == EXPECTED_CAPTIVE,
              f"{len(cap_blocks)} blocks, {math.fsum(b['_mw'] for b in cap_blocks):,.1f} MW (expected {EXPECTED_CAPTIVE[0]} / {EXPECTED_CAPTIVE[1]:,})")
        check("dc_ppa", args.no_count_check or (len(ppa_blocks), round(math.fsum(b['_mw'] for b in ppa_blocks))) == EXPECTED_PPA,
              f"{len(ppa_blocks)} blocks, {math.fsum(b['_mw'] for b in ppa_blocks):,.1f} MW (expected {EXPECTED_PPA[0]} / {EXPECTED_PPA[1]:,})")
        check("both flags on one block", len(both) == 0, f"{len(both)} blocks (September: 0)")
        n_appr = sum(1 for b in blocks if b["location_accuracy"] == "approximate")
        check("approximate points", args.no_count_check or n_appr == EXPECTED_APPROX, f"{n_appr:,} (expected {EXPECTED_APPROX:,})")
        check("iso3_gem / iso3_source filled", all(b["iso3_gem"] and b["iso3_source"] for b in blocks), "every row")
        n_zero = [b["record_id"] for b in blocks if b["_mw"] == 0]

        if fails:
            raise Stop("checks failed: " + " | ".join(fails))

        # --- write
        written = {}
        for ds in sets:
            for kind, df in zip(names[ds], (units_df[ds], places_df[ds])):
                p = out_dir / f"{kind}.csv"
                write_csv(df, p)
                written[p.name] = p
        written[sg_path.name] = sg_path
        written[map_path.name] = map_path
        cpath = rules_dir / "gem_country_table.csv"
        used = sorted({b["country_area"] for b in blocks})
        write_csv(pd.DataFrame([(nm, by_name[nm]) for nm in sorted(by_name)], columns=["gem_country_name", "iso3_gem"]), cpath)
        written[cpath.name] = cpath
        hashes = {n: sha256_file(p) for n, p in sorted(written.items())}
        hpath = out_dir / "build_hashes.json"
        prev = json.loads(hpath.read_text(encoding="utf-8")) if hpath.exists() else None
        hpath.write_text(json.dumps({"input_sha256": sha_in, "files": hashes}, indent=2) + "\n", encoding="utf-8")
        same = None if prev is None else (prev.get("files") == hashes and prev.get("input_sha256") == sha_in)

        # --- extras
        res_dir.mkdir(parents=True, exist_ok=True)
        mism = Counter((b["iso3_source"], b["iso3_frame"], b["iso3_frame_rule"]) for b in blocks if b["iso3_source"] != b["iso3_frame"])
        with open(res_dir / "iso3_source_vs_frame.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["record_id", "country_area", "iso3_gem", "iso3_source", "iso3_frame", "iso3_frame_rule", "control_iso3", "lon", "lat"])
            for b in sorted(blocks, key=lambda b: b["record_id"]):
                if b["iso3_source"] != b["iso3_frame"]:
                    w.writerow([b["record_id"], b["country_area"], b["iso3_gem"], b["iso3_source"], b["iso3_frame"], b["iso3_frame_rule"], b["control_iso3"], b["lon"], b["lat"]])
        with open(res_dir / "places_wide_spread.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["dataset", "location_id", "plant_name", "country_area", "n_units", "lon_spread_deg", "lat_spread_deg"])
            for r in sorted(wide_rows, key=lambda r: (-max(r[5], r[6]), r[1])):
                w.writerow(r)
        with open(res_dir / "places_split_by_point.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["dataset", "location_id", "plant_name", "n_units", "n_point_groups"])
            for r in sorted(split_rows, key=lambda r: (r[0], r[1])):
                w.writerow(r)

        # --- report
        rule_cnt = Counter(b["iso3_frame_rule"] or "(empty)" for b in blocks)
        L = ["# build_report · GEM plants · abf-energy / abf-energync 0.1.0", "",
             f"Built: {time.strftime('%Y-%m-%d %H:%M:%S')} (local) · took {time.time() - t0:.0f} s · SPEC_GEM_plants_v0_1_0 r4", "",
             f"- Input: `{gipt}` · SHA-256 `{sha_in}`",
             f"- Frame: `{args.frame_dir}` · adm0.parquet `{frame.p0_sha[:16]}…` · contested_areas.parquet `{frame.pc_sha[:16]}…`",
             f"- Country sheet name column (exact): `{cname_col}`",
             f"- Rerun: " + ("first run, nothing to compare" if same is None else ("**identical** to the previous run (all SHA-256 equal)" if same else "**DIFFERENT** from the previous run")),
             "", "## Checks (section 2.7)", "", "| check | result | detail |", "|---|---|---|"] + report
        L += ["", "## Files", "", "| file | bytes | SHA-256 |", "|---|---:|---|"]
        for n, p in sorted(written.items()):
            L.append(f"| {n} | {p.stat().st_size:,} ({p.stat().st_size / 1e6:.1f} MB; {p.stat().st_size / 1048576:.1f} MiB) | `{hashes[n]}` |")
        big = [n for n, p in written.items() if p.stat().st_size > 50 * 1e6]
        L.append("")
        L.append("Files over 50 MB decimal, which is 47.7 MiB (tell V before commit; the SPEC says 50 MB, GitHub counts MiB): " + (", ".join(big) if big else "none"))
        L += ["", "## Counts", "", "| set | blocks | locations | places | locations split by point groups | places with n_units_other_set > 0 | their locations |", "|---|---:|---:|---:|---:|---:|---:|"]
        for ds in sets:
            L.append(f"| {ds} | {len(sets[ds]):,} | {place_stats[ds]['n_locations']:,} | {len(place_stats[ds]['places']):,} | {place_stats[ds]['n_split']:,} | {sum(1 for p in place_stats[ds]['places'] if p['n_units_other_set'] != '0'):,} | {len({p['location_id'] for p in place_stats[ds]['places'] if p['n_units_other_set'] != '0'}):,} |")
        L += ["", "Places by status_group x capacity_class:", ""]
        for ds in sets:
            ct = pd.crosstab(places_df[ds]["status_group"], places_df[ds]["capacity_class"])
            L += [f"`{ds}`", "", "```", ct.to_string(), "```", ""]
        L += ["## MW by type x status_group (blocks)", ""]
        for ds, bl in sets.items():
            t = pd.DataFrame([{"type": b["type"], "status_group": b["status_group"], "mw": b["_mw"]} for b in bl])
            pv = t.pivot_table(index="type", columns="status_group", values="mw", aggfunc=lambda s: math.fsum(s), fill_value=0)
            pv["TOTAL"] = pv.sum(axis=1)
            L += [f"`{ds}`", "", "```", pv.round(0).astype(int).to_string(), "```", ""]
        empty_f = Counter(b["iso3_source"] for b in blocks if not b["iso3_frame"])
        real_m = Counter((b["iso3_source"], b["iso3_frame"], b["iso3_frame_rule"]) for b in blocks if b["iso3_frame"] and b["iso3_source"] != b["iso3_frame"])
        ctl = Counter((b["iso3_source"], b["control_iso3"]) for b in blocks if b["control_iso3"])
        L += ["## Country", "", f"- iso3_frame_rule: {dict(rule_cnt)}",
              f"- ADM0 overlaps resolved by iso3_gem: {n_overlap} points; points in zones with different controlled_by: {n_multi}",
              f"- rows with iso3_source != iso3_frame: {sum(mism.values()):,}, of them iso3_frame empty (farther than 22.2 km from land): {sum(empty_f.values()):,}; "
              f"both filled but different: {sum(real_m.values()):,} (full list: `research\\gem\\iso3_source_vs_frame.csv`)", "",
              "Both filled, different:", "", "| iso3_source | iso3_frame | rule | rows |", "|---|---|---|---:|"]
        for (s_, f_, r_), n in real_m.most_common(40):
            L.append(f"| {s_} | {f_} | {r_} | {n:,} |")
        L += ["", "iso3_frame empty, by iso3_source (top 25):", "", "| iso3_source | rows |", "|---|---:|"]
        for s_, n in empty_f.most_common(25):
            L.append(f"| {s_} | {n:,} |")
        L += ["", f"Rows inside a contested_areas zone (control_iso3 filled): {sum(ctl.values()):,}", "", "| iso3_source | control_iso3 | rows |", "|---|---|---:|"]
        for (s_, c_), n in ctl.most_common(20):
            L.append(f"| {s_} | {c_} | {n:,} |")
        L += ["", f"- rows of `gem_iso3_to_adm0.csv`: {len(map_rows)} (accepted by the script: {len(auto_rows)}, manual from RES: {len(manual)})"]
        for r in map_rows:
            L.append(f"  - {r['iso3_gem']} -> {r['iso3_source']} · {r['reason']}")
        L += ["", "## For [RES]7", "",
              f"- locations whose blocks (all types and statuses together) spread more than 1 degree in lon or lat: {len(wide_rows)} (list: `research\\gem\\places_wide_spread.csv`)",
              f"- places split by point groups (1 km): {sum(place_stats[d]['n_split'] for d in sets):,} (list: `research\\gem\\places_split_by_point.csv`)",
              f"- blocks with 0 MW: {[(b['record_id'], b['plant_name'], b['type'], b['status'], b['country_area']) for b in blocks if b['_mw'] == 0]}", f"- country names in the data: {len(used)}"]
        (out_dir / "build_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        LOG.info("DONE in %.0f s. Report: %s", time.time() - t0, out_dir / "build_report.md")
        return 0
    except Stop as e:
        LOG.error("STOP: %s", e)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "build_report.md").write_text("# build_report · STOP\n\n" + str(e) + "\n\n| check | result | detail |\n|---|---|---|\n" + "\n".join(report) + "\n", encoding="utf-8")
        return 1


def csv_cell(v) -> str:
    s = str(v)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s


if __name__ == "__main__":
    sys.exit(main())
