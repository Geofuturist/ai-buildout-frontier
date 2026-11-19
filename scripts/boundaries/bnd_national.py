#!/usr/bin/env python3
"""
bnd_national.py -- abf-boundaries 0.3.0: one general adapter for ADM1 taken from national sources
(SPEC_BND_boundaries_v0_3_0.md r4 S4: "a country is a row of boundaries/national_sources_v030.csv, not a branch of code").

Imported by build_boundaries.py and validate_boundaries.py. The USA / Norway builders are not touched.

Table  boundaries/national_sources_v030.csv  (one row = one PART of a country; a country may have several parts,
e.g. LVA = Novadi + Pilsetas, NZL = regional councils + Chatham Islands Territory from the TA layer):
  iso3, part, source ("file", "archive.zip!inner/path.shp" (glob allowed), or "archive.gdb.zip" + layer),
  layer, filter (pandas query on the raw columns), group_field (dissolve by it: IRL, TWN),
  regroup ("field~regex=>NEWCODE|NEWNAME": rows whose field matches get this code/name: PHL Negros Island Region),
  code_field, name_field, code_strip (prefix cut from the code: MX, TH, VN, PH), merge ("CODE:name part+CODE:name part=NEWCODE",
  the name part is a guard: the build stops if the file's name does not contain it), id_scheme (national|iso),
  iso_rule ("EE-{last2}", "TH-{code}"), cldr_name_match (yes = match the source name to the English CLDR name),
  crs_override, neighbours (ISO3; list), sea (none|clip: clip DISPLAY geometry to the ADM0 polygon, HKG),
  coord_decimals (IDN: 4), unit_type_local/en, vintage (date, or "field:valid_on"), publisher, product, url, license,
  attribution, expected_units (G3, per part), accept_points ("lon lat=>unit_id"), tag (analysis file name), note.
Names table  boundaries/adm1_names_v030.csv : iso3, national_code, iso_3166_2, name_en, note.

Rules (SPEC r4 S2, S3b):
  * analysis geometry = the official polygons as they are (reprojected to WGS84, dissolved/merged as the table says);
  * display geometry = national_conformed (ADR 5.4): neighbours' ADM0 removed, land gaps along the border handed to the
    unit with the longest common boundary, water and coast mismatch not filled; sea = clip -> display clipped to the ADM0.
    NOTE (differs from the US/NOR conform): a gap part is filled only inside a corridor around the land border
    (CORRIDOR_DEG), otherwise a coastline mismatch connected to the border end would be handed to one unit as a strip.
  * unit_id = <ISO3>-1-<national code> (or ISO 3166-2 suffix for id_scheme = iso); name = English CLDR name when the unit
    is mapped to an ISO 3166-2 code, else the name of the source (Latin script).
  * coord_decimals: the LAST step of the display geometry is a topology-preserving rounding of the whole coverage to that many
    decimals (IDN: Perban BIG 1/2026 art. 5(1)); unit geometry is valid after rounding, or the build stops.

v0.3.0 r5 (SPEC_BND_boundaries_v0_3_0.md S3g, ARCH7 16.11) -- order of the DISPLAY geometry of a national country:
    official units -> clean the coverage (overlaps and slivers narrower than GAP_WIDTH_DEG between two units; always for a country
    whose coverage is not valid) -> coverage simplification with shared edges kept identical (SIMPLIFY_TOL_DEG = 0.0005 deg, ~55 m;
    one unit may not lose more than 2 % of its area, none may vanish) -> conform (neighbours' ADM0 AND the already published ADM1 of
    the neighbours are removed, land gaps along the border are handed over) -> rounding (countries with coord_decimals).
    analysis/ keeps the full detail of the official polygons.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pickle
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnd_common as c  # noqa: E402

TABLE_COLUMNS = [
    "iso3", "part", "source", "layer", "filter", "group_field", "regroup", "code_field", "name_field", "code_strip", "merge",
    "id_scheme", "iso_rule", "cldr_name_match", "crs_override", "neighbors", "sea", "coord_decimals", "unit_type_local",
    "unit_type_en", "vintage", "publisher", "product", "url", "license", "attribution", "expected_units", "accept_points",
    "tag", "note",
]
NAMES_COLUMNS = ["iso3", "national_code", "iso_3166_2", "name_en", "note"]
ISO2 = {"LUX": "LU", "LVA": "LV", "EST": "EE", "PER": "PE", "NZL": "NZ", "TWN": "TW", "HKG": "HK", "IRL": "IE", "KOR": "KR",
        "MEX": "MX", "COL": "CO", "IDN": "ID", "PHL": "PH", "THA": "TH", "VNM": "VN"}
CORRIDOR_DEG = 0.10          # ~11 km: land gaps are handed over only this close to the land border with a neighbour
OUTSIDE_STOP_SHARE = 0.25    # share of national area outside the ADM0 polygon above which a country without sea=clip stops
LAND_RESIDUAL_TOL_KM2 = c.CONFORM_RESIDUAL_TOL_KM2
GAP_WIDTH_DEG = 0.0005       # ~55 m: slivers between two units narrower than this are closed (coverage cleaning)
SIMPLIFY_TOL_DEG = 0.0005    # ~55 m: coverage simplification of the DISPLAY geometry (ARCH7 D5)
TILE_MODE_VERTICES = 250_000  # sliver search of two parts with more vertices than this works tile by tile
TILE_MODE_MIN_AREA_DEG2 = 0.25
TILE_DEG = 0.05
TINY_OVERLAP_KM2 = 1e-4  # overlap pieces smaller than this (100 m2) are handed over without a boundary test
COVERAGE_INVALID_EDGE_TOL_KM = 20.0  # edges not matching a neighbour after simplification: more than this = problem (check 13)
SIMPLIFY_LOSS_STOP = 0.02    # a unit that loses more than 2 % of its area in the simplification stops the build (RES)
LOST_PART_KEEP = 0.5         # a part of the official unit is "lost" if less than this share of it is left after simplification
IDN_NEIGHBOUR_PAIR_TOL_KM2 = 1.0   # D1: check 1, one pair of a rounded country (IDN) with a neighbour (MYS, PNG, TLS)
IDN_COUNTRY_RESIDUAL_TOL_KM2 = 5.0  # D1: check 3, residual of a rounded country (encroachment, land gap) per country


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def load_table(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    miss = [k for k in TABLE_COLUMNS if k not in df.columns]
    if miss:
        raise c.BuildError(f"{path}: columns missing: {miss}")
    if df.duplicated(["iso3", "part"]).any():
        raise c.BuildError(f"{path}: duplicate (iso3, part)")
    # optional flags (ARCH7 18.11): clean = full (default) | overlaps | no ; simplify = yes (default) | no
    for col, ok in (("clean", {"full", "overlaps", "no"}), ("simplify", {"yes", "no"})):
        if col not in df.columns:
            df[col] = ""
        bad = sorted(set(df[col].str.strip().str.lower()) - ok - {""})
        if bad:
            raise c.BuildError(f"{path}: column {col}: value(s) {bad} not allowed (allowed: {sorted(ok)} or empty)")
    return df


def load_names(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=NAMES_COLUMNS)
    df = _read_csv(path)
    miss = [k for k in NAMES_COLUMNS if k not in df.columns]
    if miss:
        raise c.BuildError(f"{path}: columns missing: {miss}")
    return df


def expected_per_country(table: pd.DataFrame) -> dict[str, int]:
    return {iso: int(g["expected_units"].astype(int).sum()) for iso, g in table.groupby("iso3")}


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def _posix(p: Path) -> str:
    return str(p).replace("\\", "/")


def _find_file(root: Path, iso3: str, fname: str) -> Path:
    folder = root / iso3.lower()
    p = folder / fname
    if p.exists():
        return p
    if folder.exists():
        for q in folder.rglob("*"):
            if q.is_file() and q.name.lower() == Path(fname).name.lower() and "_old" not in [x.lower() for x in q.parts]:
                return q
    raise c.BuildError(f"{iso3}: input file {fname!r} not found in {folder} (SPEC r4 S3v p.4)")


def locate(root: Path, row) -> tuple[str, Optional[str], Path]:
    """-> (source string for read_file, layer, physical file)."""
    iso3, source, layer = row["iso3"], row["source"], row["layer"] or None
    fname, inner = (source.split("!", 1) + [None])[:2] if "!" in source else (source, None)
    fpath = _find_file(root, iso3, fname)
    if fpath.suffix.lower() == ".zip":
        if inner:
            with zipfile.ZipFile(fpath) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
            hit = [n for n in names if fnmatch.fnmatch(n, inner) or fnmatch.fnmatch(Path(n).name, inner)
                   or fnmatch.fnmatch(n, "*" + inner)]
            if len(hit) != 1:
                raise c.BuildError(f"{iso3}: {len(hit)} entries match {inner!r} in {fpath.name}: {hit[:5]}")
            return "/vsizip/" + _posix(fpath) + "/" + hit[0], layer, fpath
        return "/vsizip/" + _posix(fpath), layer, fpath
    return str(fpath), layer, fpath


ATTRIBUTES_ONLY = False  # names-preview mode: read the attribute tables only, geometry is a dummy box


def read_source(src: str, layer: Optional[str]) -> gpd.GeoDataFrame:
    """Read with the same encoding handling as the pre-flight: try encodings until no U+FFFD in text, fix UTF-8 read as latin1."""
    last = None
    for enc in (None, "cp949", "utf-8", "cp1252", "big5", "latin1"):
        try:
            kw = {"layer": layer} if layer else {}
            if enc:
                kw["encoding"] = enc
            if ATTRIBUTES_ONLY:
                import pyogrio
                df = pyogrio.read_dataframe(src, read_geometry=False, **kw)
                g = gpd.GeoDataFrame(df, geometry=[shapely.box(0, 0, 1e-3, 1e-3)] * len(df), crs=c.CRS_WGS84)
            else:
                g = gpd.read_file(src, engine="pyogrio", **kw)
            bad = 0
            for col in g.columns:
                if col != "geometry" and str(g[col].dtype) in ("object", "str", "string"):
                    bad += int(g[col].astype(str).str.contains("�").sum())
            for col in g.columns:
                if col != "geometry" and str(g[col].dtype) in ("object", "str", "string"):
                    def _fx(v):
                        if isinstance(v, str) and re.search("[Â-Å][\u0080-¿]", v):
                            try:
                                return v.encode("latin1").decode("utf-8")
                            except Exception:  # noqa: BLE001
                                return v
                        return v
                    g[col] = g[col].map(_fx)
            if bad == 0 or enc == "latin1":
                return g
            last = g
        except Exception as e:  # noqa: BLE001
            last = e
    if isinstance(last, Exception):
        raise last
    return last


# --------------------------------------------------------------------------
# Preparing one part
# --------------------------------------------------------------------------

def _s(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    s = str(v).strip()
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def norm_code(code: str) -> str:
    code = str(code).strip()
    return (code.lstrip("0") or "0") if code.isdigit() else code


def _vintage(spec: str, gdf: gpd.GeoDataFrame, fpath: Optional[Path] = None) -> str:
    if spec == "retrieved":
        # the issuer gives no date we could read: the date the file was saved (reported as such, RES to replace by the real one)
        if fpath is None:
            return "retrieved"
        return time.strftime("%Y-%m-%d", time.gmtime(fpath.stat().st_mtime))
    if spec.startswith("field:"):
        col = spec[6:]
        if col not in gdf.columns:
            raise c.BuildError(f"vintage: column {col!r} not in the source (columns: {list(gdf.columns)[:30]})")
        vals = sorted({_s(v)[:10] for v in gdf[col] if _s(v)})
        if not vals:
            raise c.BuildError(f"vintage: column {col!r} is empty")
        return vals[-1]
    return spec


def prepare_part(row, gdf: gpd.GeoDataFrame, fpath: Optional[Path] = None, proof_root: Optional[Path] = None) -> tuple[gpd.GeoDataFrame, dict]:
    """Raw layer -> units of this part: columns code, name_src, src_ref, geometry (EPSG:4326, cleaned)."""
    iso3 = row["iso3"]
    info = {"raw_n": len(gdf), "columns": [x for x in gdf.columns if x != "geometry"]}
    if row["crs_override"]:
        gdf = gdf.set_crs(row["crs_override"], allow_override=True)
    if row["filter"]:
        gdf = gdf.query(row["filter"], engine="python")
        info["after_filter_n"] = len(gdf)
    gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty].copy()
    for fld in (row["code_field"], row["group_field"]):
        if fld and fld not in gdf.columns:
            raise c.BuildError(f"{iso3} part {row['part']}: field {fld!r} not in the source; columns: {info['columns']}")
    info["vintage"] = _vintage(row["vintage"], gdf, fpath)
    info["vintage_is_retrieval_date"] = row["vintage"] == "retrieved"
    gdf = c.to_wgs84(gdf)
    gdf = gdf.reset_index(drop=True)
    gdf["geometry"] = [shapely.make_valid(g) for g in gdf.geometry.values]

    code = gdf[row["code_field"]].map(_s)
    name = gdf[row["name_field"]].map(_s) if row["name_field"] and row["name_field"] in gdf.columns else pd.Series([""] * len(gdf))
    pre = row["code_strip"]
    if pre:
        code = code.map(lambda x: x[len(pre):] if x.startswith(pre) else x)
    grp = gdf[row["group_field"]].map(_s) if row["group_field"] else None
    if grp is not None and pre:
        grp = grp.map(lambda x: x[len(pre):] if x.startswith(pre) else x)

    regroup_name = {}
    if row["regroup"]:
        # one or more rules separated by ' ;; ':  field~regex=>NEWCODE[|NEWNAME][#proof:regex]
        #   NEWNAME given = a new unit (PHL NIR); no NEWNAME = the rows join the existing unit NEWCODE (PHL Sulu -> Region IX).
        #   proof = a regex that must be found in the text of a page saved in the country folder (the legal act): without it the rule
        #   is NOT applied and the source file is shown as it is (reported in info['regroup_skipped']).
        grp = grp.copy()
        code = code.copy()
        info["regroup"], info["regroup_skipped"] = [], []
        for rule in [x.strip() for x in row["regroup"].split(" ;; ") if x.strip()]:
            m = re.fullmatch(r"([^~]+)~(.+?)=>([^|#]+)(?:\|([^#]+))?(?:#proof:(.+))?", rule)
            if not m:
                raise c.BuildError(f"{iso3}: cannot read regroup {rule!r}")
            fld, rx, ncode, nname, proof = m.groups()
            if fld not in gdf.columns:
                raise c.BuildError(f"{iso3}: regroup field {fld!r} not in the source")
            if proof:
                found = text_proof(proof_root, iso3, proof) if proof_root is not None else dict(found=False, line="no input root")
                if not found["found"]:
                    info["regroup_skipped"].append(dict(rule=rule, reason=f"proof not found in the saved pages: {found['line']}"))
                    continue
                proof_line = found["line"]
            else:
                proof_line = ""
            hit = gdf[fld].map(_s).str.contains(rx, regex=True)
            if int(hit.sum()) == 0:
                raise c.BuildError(f"{iso3}: regroup rule {rule!r} matches no row of the source (values of {fld!r}: "
                                   f"{sorted(set(gdf[fld].map(_s)))[:60]})")
            if not nname and ncode not in set(grp):
                raise c.BuildError(f"{iso3}: regroup target {ncode!r} is not an existing unit (groups: {sorted(set(grp))})")
            before = sorted(set(grp[hit]))
            rec = dict(rule=rule, rows=int(hit.sum()), names=sorted(gdf.loc[hit, fld].map(_s).tolist()), from_groups=before,
                       to=ncode, proof=proof_line)
            grp[hit] = ncode
            code[hit] = ncode
            if nname:
                regroup_name[ncode] = nname
            rec["groups_after"] = {g: sorted(gdf.loc[grp == g, fld].map(_s).tolist()) for g in sorted(set(before) | {ncode})}
            info["regroup"].append(rec)
        info["regroup_rows"] = sum(r["rows"] for r in info["regroup"])
        info["regroup_names"] = sorted(n for r in info["regroup"] for n in r["names"])

    gdf = gdf.assign(_code=code.values, _name=name.values)
    if grp is not None:
        gdf["_grp"] = grp.values
        keyc = "_grp"
    else:
        keyc = "_code"
    if grp is not None:
        # only whole units are dissolved; Sanhe-type extras are excluded by the table's file choice
        agg = gdf.groupby(keyc, sort=True)
        rows = []
        for key, g in agg:
            geom = c.union_clean(g.geometry.values)
            nm = regroup_name.get(key) or next((x for x in g["_name"] if x), "")
            rows.append(dict(code=key, name_src=nm, src_ref=key, n_raw=len(g), geometry=geom))
        out = gpd.GeoDataFrame(rows, crs=c.CRS_WGS84)
        info["dissolved_from"] = len(gdf)
    else:
        out = gpd.GeoDataFrame(dict(code=gdf["_code"].values, name_src=gdf["_name"].values, src_ref=gdf["_code"].values,
                                    n_raw=1, geometry=[c.clean(g) for g in gdf.geometry.values]), crs=c.CRS_WGS84)
    if out["code"].eq("").any():
        raise c.BuildError(f"{iso3} part {row['part']}: empty national code in {int(out['code'].eq('').sum())} unit(s)")
    out["part"] = int(row["part"])
    return out, info


def apply_merge(iso3: str, units: gpd.GeoDataFrame, spec: str) -> tuple[gpd.GeoDataFrame, dict]:
    """KOR: 'CODE:guard+CODE:guard=NEWCODE' -- units are merged into one; the guard must occur in the file's name."""
    m = re.fullmatch(r"(.+)=([^=]+)", spec)
    if not m:
        raise c.BuildError(f"{iso3}: cannot read merge {spec!r}")
    items, newcode = m.groups()
    parts = []
    for it in items.split("+"):
        code, guard = it.split(":", 1)
        parts.append((code.strip(), guard.strip()))
    sel = []
    for code, guard in parts:
        hit = units[units["code"].map(norm_code) == norm_code(code)]
        if len(hit) != 1:
            raise c.BuildError(f"{iso3}: merge code {code!r} found {len(hit)} times; codes and names in the file: "
                               f"{list(zip(units['code'], units['name_src']))}")
        if guard not in hit["name_src"].iloc[0]:
            raise c.BuildError(f"{iso3}: merge code {code!r} is {hit['name_src'].iloc[0]!r} in the file, the guard says it must "
                               f"contain {guard!r}. Codes and names in the file: {list(zip(units['code'], units['name_src']))}")
        sel.append(hit.index[0])
    sub = units.loc[sel]
    geom = c.union_clean(sub.geometry.values)
    new = dict(code=newcode, name_src="", src_ref=";".join(sub["code"].tolist()), n_raw=int(sub["n_raw"].sum()), geometry=geom,
               part=int(sub["part"].iloc[0]))
    info = dict(merged_codes=sub["code"].tolist(), merged_names=sub["name_src"].tolist(), result_type=geom.geom_type,
                parts_touch=bool(shapely.intersects(sub.geometry.iloc[0], sub.geometry.iloc[1])) if len(sub) == 2 else None)
    rest = units.drop(index=sel)
    out = pd.concat([rest, gpd.GeoDataFrame([new], crs=c.CRS_WGS84)], ignore_index=True)
    return gpd.GeoDataFrame(out, crs=c.CRS_WGS84), info


def read_country(root: Path, rows: pd.DataFrame) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """All parts of a country -> units (code, name_src, src_ref, part, geometry, + per-part table fields)."""
    iso3 = rows["iso3"].iloc[0]
    frames, infos = [], []
    for _, row in rows.iterrows():
        src, layer, fpath = locate(root, row)
        gdf = read_source(src, layer)
        units, info = prepare_part(row, gdf, fpath, root)
        info.update(iso3=iso3, part=int(row["part"]), file=fpath.name, path=str(fpath), sha256=c.sha256_file(fpath),
                    retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fpath.stat().st_mtime)),
                    n_units=len(units), expected=int(row["expected_units"]))
        if row["merge"]:
            units, minfo = apply_merge(iso3, units, row["merge"])
            info["merge"] = minfo
            info["n_units"] = len(units)
        if len(units) != int(row["expected_units"]):
            raise c.BuildError(f"{iso3} part {row['part']}: {len(units)} units, expected {row['expected_units']} (G3); "
                               f"codes: {units['code'].tolist()[:40]}")
        units["unit_type_local"] = row["unit_type_local"]
        units["unit_type_en"] = row["unit_type_en"]
        units["vintage"] = info["vintage"]
        units["publisher"] = row["publisher"]
        units["product"] = row["product"]
        frames.append(units)
        infos.append(info)
    allu = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=c.CRS_WGS84)
    if allu["code"].duplicated().any():
        raise c.BuildError(f"{iso3}: duplicate national code(s): {allu['code'][allu['code'].duplicated()].tolist()}")
    return allu, infos


# --------------------------------------------------------------------------
# CLDR names / ISO 3166-2
# --------------------------------------------------------------------------

_GENERIC = {"county", "co", "region", "province", "municipality", "city", "department", "state", "district", "prefecture",
            "autonomous", "special", "metropolitan", "of", "the", "de", "departamento", "provincia"}


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    toks = [t for t in s.split() if t not in _GENERIC]
    return " ".join(toks) if toks else s


def _names_related(a: str, b: str) -> bool:
    """Do two names share a word, or the first five letters of a word (Aizkraukles / Aizkraukle, Sumatera / Sumatra)?"""
    ta, tb = norm_name(a).split(), norm_name(b).split()
    if set(ta) & set(tb):
        return True
    return any(x[:5] == y[:5] for x in ta for y in tb if len(x) >= 5 and len(y) >= 5)


def to_cldr(iso: str) -> str:
    """ISO 3166-2 'LU-CA' -> CLDR subdivision id 'luca'."""
    return iso.replace("-", "").lower()


def from_cldr(code: str, cc: str) -> str:
    return f"{cc}-{code[2:].upper()}"


class Cldr:
    def __init__(self, manifest: dict):
        import xml.etree.ElementTree as ET
        import bnd_plan as bp
        files = bp._cldr_files(manifest)
        self.contains: dict[str, set[str]] = {}
        for sg in ET.parse(files["cldr_subdivisions"]).getroot().iter("subgroup"):
            self.contains.setdefault(sg.get("type"), set()).update(sg.get("contains", "").split())
        self.names: dict[str, list[tuple[str, str]]] = {}
        for sd in ET.parse(files["cldr_subdivisions_en"]).getroot().iter("subdivision"):
            self.names.setdefault(sd.get("type"), []).append((sd.get("alt", ""), (sd.text or "").strip()))
        self._reach: dict[str, set[str]] = {}

    def reach(self, cc: str) -> set[str]:
        if cc not in self._reach:
            seen, stack = set(), list(self.contains.get(cc, ()))
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                stack.extend(self.contains.get(x, ()))
            self._reach[cc] = seen
        return self._reach[cc]

    def en_name(self, code: str) -> Optional[str]:
        cand = [t for alt, t in self.names.get(code, []) if alt == ""]
        return cand[0] if len(set(cand)) == 1 else None

    def direct_children(self, cc: str) -> list[str]:
        """Leaf subdivisions of the country (those that contain no other subdivision): counties of IE, provinces of ID."""
        return sorted(x for x in self.reach(cc) if not self.contains.get(x))


def resolve_names(iso3: str, units: gpd.GeoDataFrame, rows: pd.DataFrame, names_tbl: pd.DataFrame, cldr: Optional[Cldr]) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """unit_id, name, iso_3166_2 for every unit (SPEC r4 S2 p.3 and p.5). Returns (units, review rows)."""
    cc = ISO2[iso3]
    nt = names_tbl[names_tbl["iso3"] == iso3]
    by_code = {norm_code(r.national_code): r for r in nt.itertuples()}
    unknown = sorted(set(by_code) - {norm_code(x) for x in units["code"]})
    if unknown:
        raise c.BuildError(f"{iso3}: adm1_names_v030.csv has code(s) not in the source: {unknown}; codes in the source: "
                           f"{list(zip(units['code'], units['name_src']))}")
    id_scheme = rows["id_scheme"].iloc[0]
    iso_rule = rows["iso_rule"].iloc[0]
    use_match = rows["cldr_name_match"].iloc[0] == "yes"
    children = cldr.direct_children(cc) if cldr is not None else []
    child_by_norm: dict[str, list[str]] = {}
    for ch in children:
        nm = cldr.en_name(ch)
        if nm:
            child_by_norm.setdefault(norm_name(nm), []).append(ch)
    out_id, out_name, out_iso, review = [], [], [], []
    for u in units.itertuples():
        code, src_name = u.code, u.name_src
        iso, name, how = "", "", ""
        r = by_code.get(norm_code(code))
        if r is not None:
            iso, name, how = r.iso_3166_2.strip(), r.name_en.strip(), "table"
        if not iso and not name and iso_rule:
            digits = re.sub(r"\D", "", code)
            iso = iso_rule.format(code=code, last2=digits[-2:].zfill(2))
            how = "rule " + iso_rule
        if not iso and not name and use_match and cldr is not None:
            hit = child_by_norm.get(norm_name(src_name), [])
            if len(hit) == 1:
                iso, how = from_cldr(hit[0], cc), "cldr name match"
        if iso and cldr is not None:
            if to_cldr(iso) not in cldr.reach(cc):
                raise c.BuildError(f"{iso3} {code}: {iso} is not in the CLDR containment tree under {cc} (SPEC v0.2.0 S2.4a)")
            en = cldr.en_name(to_cldr(iso))
            if en and r is not None and r.name_en.strip() and r.name_en.strip() != en:
                how += f"; name from the table, CLDR says {en!r}"
            elif en:
                name = en
            elif not name:
                name = src_name
                how += "; no CLDR name, source name"
        elif iso and cldr is None:
            name = name or src_name
        if not name:
            name = src_name
            how = how or "source name"
        if not name:
            raise c.BuildError(f"{iso3} {code}: no name (source has none; add a row with name_en to adm1_names_v030.csv)")
        if id_scheme == "iso":
            if not iso:
                raise c.BuildError(f"{iso3} {code} {src_name!r}: id_scheme=iso but no ISO 3166-2 code could be found; "
                                   f"add it to adm1_names_v030.csv")
            uid = f"{iso3}-1-{iso.split('-', 1)[1]}"
        else:
            uid = f"{iso3}-1-{code}"
        flag = ""
        if r is not None and "project translation" in str(r.note).lower():
            how += "; project translation"
        if iso and src_name and norm_name(src_name) and norm_name(name) and not _names_related(src_name, name):
            flag = "names share no word: check the code -> ISO mapping"
        out_id.append(uid)
        out_name.append(name)
        out_iso.append(iso)
        review.append(dict(unit_id=uid, source_code=code, source_name=src_name, iso_3166_2=iso, name=name, how=how, flag=flag))
    units = units.copy()
    units["unit_id"], units["name"], units["iso_3166_2"] = out_id, out_name, out_iso
    if units["unit_id"].duplicated().any():
        raise c.BuildError(f"{iso3}: duplicate unit_id {units['unit_id'][units['unit_id'].duplicated()].tolist()}")
    return units, review


# --------------------------------------------------------------------------
# Rounding (IDN)
# --------------------------------------------------------------------------

def round_geom(geom, decimals: int):
    """Round coordinates to `decimals` decimals; the result is valid, polygonal and has no more decimals (exact doubles of the decimal)."""
    g = geom
    for _ in range(4):
        g = shapely.set_precision(g, 10.0 ** -decimals)
        g = shapely.transform(g, lambda a: np.round(a, decimals))
        if not g.is_valid:
            g = c._to_polygonal(shapely.make_valid(g))
            continue
        break
    if not g.is_valid or g.is_empty:
        raise c.BuildError(f"geometry is not valid / is empty after rounding to {decimals} decimals")
    return c._to_polygonal(g)


def max_decimals(geom, limit: int = 8) -> int:
    xy = shapely.get_coordinates(geom)
    worst = 0
    for d in range(limit + 1):
        if np.all(np.round(xy, d) == xy):
            return d
        worst = d + 1
    return worst


# --------------------------------------------------------------------------
# Coverage tools: cleaning, simplification, rounding (display geometry of a national country)
# --------------------------------------------------------------------------

def _fix(g, grid):
    """Valid polygonal geometry; with a grid the result is NOT snapped to the 1e-7 grid of c.clean (the grid of the operation stays)."""
    if g is None or g.is_empty:
        return g
    if grid:
        if not g.is_valid:
            g = shapely.make_valid(g)
        return c._to_polygonal(g)
    return c.clean(g)


def _op(fn, a, b, grid):
    return _fix(fn(a, b, grid_size=grid) if grid else fn(a, b), grid)


def _clip(g, win, grid):
    """clip_by_rect that survives a degenerate ring (GEOS raises on a ring with 3 points): falls back to a valid intersection."""
    try:
        return shapely.clip_by_rect(g, *win)
    except shapely.errors.GEOSException:
        return shapely.intersection(shapely.make_valid(g), shapely.box(*win))


def _shared_len(part, geom, tol: float, prepared: bool = False) -> float:
    """Length of the boundary of `part` lying on `geom` (within tol): the segments of the boundary of `part` whose two end points
    are both within tol of `geom` (distance test of the vertices against the part of `geom` that lies near `part`; no buffer of big
    geometries)."""
    if geom is None or geom.is_empty or part.is_empty:
        return 0.0
    if prepared:  # the caller prepared `geom` once for many calls
        g = geom
    else:
        b = part.bounds
        g = _clip(geom, (b[0] - 2 * tol, b[1] - 2 * tol, b[2] + 2 * tol, b[3] + 2 * tol), None)  # only what lies near the part
        if g.is_empty:
            return 0.0
        shapely.prepare(g)
    total = 0.0
    for poly in c.explode_parts(part):
        if poly.geom_type != "Polygon":
            continue
        for ring in [poly.exterior, *poly.interiors]:
            xy = np.asarray(ring.coords)
            if len(xy) < 2:
                continue
            near = shapely.dwithin(g, shapely.points(xy), tol)  # prepared geometry first: 50x faster
            ok = near[:-1] & near[1:]
            if ok.any():
                d = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
                total += float(d[ok].sum())
    return total


PROGRESS = {"log": None, "last": 0.0}


def rss_mb() -> Optional[int]:
    """Memory of this process in MB (psutil if installed, else the Windows API); None if unknown."""
    try:
        import psutil
        return int(psutil.Process().memory_info().rss / 1048576)
    except Exception:  # noqa: BLE001
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize / 1048576)
    except Exception:  # noqa: BLE001
        pass
    return None


def _tick(label: str, i: int, n: int, t0: float, every: float = 20.0) -> None:
    """Progress line at most every `every` seconds (set PROGRESS['log'] = print-like callable)."""
    lg = PROGRESS["log"]
    now = time.time()
    if lg and now - PROGRESS["last"] >= every:
        PROGRESS["last"] = now
        m = rss_mb()
        lg(f"      {label}: {i}/{n} ({now - t0:.0f}s{f', memory {m} MB' if m is not None else ''})")


def clean_coverage(geoms, grid: Optional[float] = None, gap_width: float = GAP_WIDTH_DEG, overlaps_only: bool = False,
                   priority: Optional[list] = None) -> tuple[list, dict]:
    """Cleaning of a whole coverage (see _clean_core), done cluster by cluster: the polygons of all units are split into parts
    (islands, mainland pieces); parts closer than gap_width (or overlapping) form a cluster; a cluster that holds parts of one unit
    only needs nothing; every cluster of two or more units is cleaned on its own (pieces of the units inside the cluster) and the
    units are put together again from the untouched parts and the cleaned pieces. The result is the same as cleaning the whole
    coverage at once, but the work grows with the size of the largest cluster (one big island), not of the whole archipelago.
    overlaps_only (table flag clean=overlaps, ARCH7 18.11 for IDN): only overlaps are taken out, gaps are NOT closed; in a pair of
    overlapping units the common part stays with the unit of the smaller priority number (`priority[k]`, here the order of the
    national codes) and is subtracted from the other one."""
    G = [_fix(g, grid) for g in geoms]
    n = len(G)
    parts, owner = [], []
    for k, g in enumerate(G):
        for p in c.explode_parts(g):
            if p.geom_type == "Polygon" and not p.is_empty:
                parts.append(p)
                owner.append(k)
    owner_a = np.array(owner)
    arr = np.array(parts, dtype=object)
    t0 = time.time()
    tree = shapely.STRtree(arr)
    if overlaps_only:  # only parts that really touch or overlap can have an overlap: much smaller clusters
        ia, ib = tree.query(arr, predicate="intersects")
    else:
        ia, ib = tree.query(arr, predicate="dwithin", distance=gap_width)
    root = list(range(len(parts)))

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    for i, j in zip(ia, ib):
        if i < j:
            ri, rj = find(int(i)), find(int(j))
            if ri != rj:
                root[rj] = ri
    clusters: dict[int, list[int]] = {}
    for k in range(len(parts)):
        clusters.setdefault(find(k), []).append(k)
    multi = [m for m in clusters.values() if len(set(owner_a[m])) > 1]
    if PROGRESS["log"]:
        PROGRESS["log"](f"      cleaning: {len(parts)} parts, {len(clusters)} cluster(s), {len(multi)} with two or more units "
                        f"(largest: {max((len(m) for m in multi), default=0)} parts) ({time.time() - t0:.0f}s)")
    rep = {"overlap_pairs": 0, "overlap_km2": 0.0, "gap_parts": 0, "gap_km2": 0.0, "units_changed": []}
    new_parts: dict[int, list] = {k: [] for k in range(n)}
    in_multi = set()
    changed = set()
    t1 = time.time()
    multi.sort(key=lambda m: -len(m))
    for ci, m in enumerate(multi):
        in_multi.update(m)
        owners = sorted(set(int(x) for x in owner_a[m]))
        pieces = []
        for o in owners:
            ps = [parts[k] for k in m if owner[k] == o]
            pieces.append(ps[0] if len(ps) == 1 else shapely.multipolygons(ps))
        if PROGRESS["log"]:
            PROGRESS["log"](f"      cluster {ci + 1}/{len(multi)}: {len(m)} parts of {len(owners)} units, "
                            f"{sum(shapely.get_num_coordinates(x) for x in pieces)} vertices ({time.time() - t1:.0f}s)")
        out, r = _clean_core(pieces, grid, gap_width, overlaps_only=overlaps_only,
                             priority=[priority[o] for o in owners] if priority is not None else None)
        for o, g in zip(owners, out):
            new_parts[o].extend(q for q in c.explode_parts(g) if q.geom_type == "Polygon" and not q.is_empty)
        for key in ("overlap_pairs", "overlap_km2", "gap_parts", "gap_km2", "overlap_tiny_pieces", "overlap_tiny_km2"):
            rep[key] = rep.get(key, 0) + r.get(key, 0)
        changed.update(owners[x] for x in r["units_changed"])
    for k, p in enumerate(parts):
        if k not in in_multi:
            new_parts[owner[k]].append(p)
    out = []
    for k in range(n):
        ps = new_parts[k]
        if not ps:
            raise c.BuildError(f"coverage cleaning: unit {k} became empty")
        out.append(_fix(ps[0] if len(ps) == 1 else shapely.multipolygons(ps), grid))
    rep["overlap_km2"] = round(rep["overlap_km2"], 4)
    rep["gap_km2"] = round(rep["gap_km2"], 4)
    rep["units_changed"] = sorted(changed)
    rep["overlap_tiny_km2"] = round(rep.get("overlap_tiny_km2", 0.0), 6)
    rep["clusters"] = len(clusters)
    rep["clusters_cleaned"] = len(multi)
    rep["mode"] = "overlaps only (gaps not closed)" if overlaps_only else "overlaps and slivers"
    return out, rep


def _clean_core(geoms, grid: Optional[float] = None, gap_width: float = GAP_WIDTH_DEG, overlaps_only: bool = False,
                priority: Optional[list] = None) -> tuple[list, dict]:
    """Make a set of unit polygons a coverage without overlaps and without slivers between two units (ADR 5.4):
    an overlap is taken out of both units and handed to the unit with the longest common boundary with it; a sliver (gap
    narrower than gap_width that touches two units) goes to the unit with the longest common boundary. Gaps open to the sea
    that touch one unit only (coast) are left. With `grid` every operation is done on that grid (rounding step).
    Works on the PARTS (islands / pieces) of the units, so that a test of two neighbours looks only at the parts that are near
    each other, not at all vertices of both units."""
    G = [_fix(g, grid) for g in geoms]
    n = len(G)
    rep = {"overlap_pairs": 0, "overlap_km2": 0.0, "gap_parts": 0, "gap_km2": 0.0, "units_changed": []}
    P: list = []
    O: list[int] = []
    for k, g in enumerate(G):
        for q in c.explode_parts(g):
            if q.geom_type == "Polygon" and not q.is_empty:
                P.append(q)
                O.append(k)
    touched: set[int] = set()
    changed: set[int] = set()
    tol = max(grid or 0.0, 1e-7) * 2
    n0 = len(P)
    tree = shapely.STRtree(np.array(P, dtype=object))

    def near_ids(box_geom, tree_, n_tree):
        ids = [int(i) for i in tree_.query(box_geom, predicate="intersects")]
        if len(P) > n_tree:
            for k in range(n_tree, len(P)):
                if P[k] is not None and not P[k].is_empty and shapely.intersects(P[k], box_geom):
                    ids.append(k)
        return [k for k in ids if P[k] is not None and not P[k].is_empty]

    def unit_near(o, geom, tree_, n_tree):
        """The parts of unit o that lie near `geom` (within tol), as one geometry."""
        bx = shapely.box(*shapely.bounds(geom)) if geom is not None else None
        bx = shapely.buffer(bx, tol * 2, quad_segs=1)
        ids = [k for k in near_ids(bx, tree_, n_tree) if O[k] == o]
        return shapely.union_all([P[k] for k in ids]) if ids else None

    # 1. overlaps (pairs of parts of different units)
    ia, ib = tree.query(np.array(P, dtype=object), predicate="intersects")
    pairs = sorted({(int(i), int(j)) for i, j in zip(ia, ib) if i < j and O[i] != O[j]})
    pieces = []
    t_ov = time.time()
    if PROGRESS["log"]:
        PROGRESS["log"](f"      cleaning: {n} units, {n0} parts, {len(pairs)} intersecting part pair(s) to test for overlap")
    for ip, (i, j) in enumerate(pairs):
        _tick("overlap pairs", ip, len(pairs), t_ov)
        if P[i] is None or P[j] is None or P[i].is_empty or P[j].is_empty:
            continue
        if PROGRESS["log"]:
            PROGRESS["log"](f"      overlap test {ip + 1}/{len(pairs)}: parts of {shapely.get_num_coordinates(P[i])} and "
                            f"{shapely.get_num_coordinates(P[j])} vertices")
        ov = _op(shapely.intersection, P[i], P[j], grid)
        polys = [q for q in c.explode_parts(ov) if q.geom_type == "Polygon" and q.area > 1e-15]
        if not polys:
            continue
        ov = polys[0] if len(polys) == 1 else shapely.union_all(polys)
        if overlaps_only:
            # the common part stays with the unit of the smaller priority number (code) and is taken out of the other one
            pr = priority if priority is not None else list(range(n))
            win_i, lose = (i, j) if (pr[O[i]], O[i]) <= (pr[O[j]], O[j]) else (j, i)
            P[lose] = _op(shapely.difference, P[lose], ov, grid)
            touched.add(O[lose])
            changed.add(O[lose])
        else:
            P[i] = _op(shapely.difference, P[i], ov, grid)
            P[j] = _op(shapely.difference, P[j], ov, grid)
            pieces.append((i, j, ov))
            touched.update((O[i], O[j]))
        rep["overlap_pairs"] += 1
        rep["overlap_km2"] += c.area_km2(ov)
    tiny_km2 = 0.0
    n_tiny = 0
    for i, j, ov in pieces:
        shapely.prepare(P[i])
        shapely.prepare(P[j])
        for q in c.explode_parts(ov):
            if q.geom_type != "Polygon" or q.is_empty:
                continue
            a_q = c.area_km2(q)
            if a_q < TINY_OVERLAP_KM2:
                # hairline overlap piece (noise of the borders): given to the unit of the first part without a boundary test
                owner = O[i]
                tiny_km2 += a_q
                n_tiny += 1
            else:
                owner = O[i] if _shared_len(q, P[i], tol, True) >= _shared_len(q, P[j], tol, True) else O[j]
            P.append(q)
            O.append(owner)
            touched.add(owner)
            changed.update((O[i], O[j]))
    rep["overlap_tiny_pieces"] = n_tiny
    rep["overlap_tiny_km2"] = round(tiny_km2, 6)
    # 2. slivers between two units: every pair of near parts (different units) gets a window around the place where they are near
    if PROGRESS["log"]:
        PROGRESS["log"]("      cleaning: overlaps done" + ("; gaps are not closed (overlaps only)" if overlaps_only else "; looking for near part pairs (slivers)..."))
    alive = [k for k in range(len(P)) if P[k] is not None and not P[k].is_empty]
    arr2 = np.array([P[k] for k in alive], dtype=object)
    tree2 = shapely.STRtree(arr2)
    n2 = len(P)
    if overlaps_only:
        ia, ib = np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    else:
        ia, ib = tree2.query(arr2, predicate="dwithin", distance=gap_width)
    pairs = sorted({(alive[int(i)], alive[int(j)]) for i, j in zip(ia, ib) if i < j and O[alive[int(i)]] != O[alive[int(j)]]})
    t_sl = time.time()
    if PROGRESS["log"]:
        PROGRESS["log"](f"      cleaning: {len(pairs)} close part pair(s) of two units to test for slivers")

    ex_cache = {"n": 0, "idx": np.zeros(0, dtype=int), "bnd": np.zeros((0, 4))}

    def ids2(box_geom):
        ids = [alive[int(i)] for i in tree2.query(box_geom, predicate="intersects")]
        if len(P) > n2:
            if ex_cache["n"] != len(P):  # pieces added since the tree was built: bounds kept in numpy arrays
                idx = np.array([k for k in range(n2, len(P)) if P[k] is not None and not P[k].is_empty], dtype=int)
                ex_cache.update(n=len(P), idx=idx, bnd=shapely.bounds(np.array([P[k] for k in idx], dtype=object)) if len(idx) else np.zeros((0, 4)))
            bx = box_geom.bounds
            bd = ex_cache["bnd"]
            if len(bd):
                hit = ex_cache["idx"][(bd[:, 0] <= bx[2]) & (bd[:, 2] >= bx[0]) & (bd[:, 1] <= bx[3]) & (bd[:, 3] >= bx[1])]
                ids.extend(int(k) for k in hit if shapely.intersects(P[k], box_geom))
        return [k for k in ids if P[k] is not None and not P[k].is_empty]

    r = gap_width * 0.51

    def process_window(win, oi, oj, keep=None, frags=None):
        """Close the slivers between units oi and oj inside the window. keep = box (tile): only the part of every gap piece inside
        it is taken, so that neighbouring tiles never produce the same piece twice."""
        box = shapely.box(*win)
        by_owner: dict[int, list] = {}
        loc = []
        for k in ids2(box):
            part = _clip(P[k], win, grid)
            if not part.is_empty:
                part = _fix(part, grid)
                loc.append(part)
                by_owner.setdefault(O[k], []).append(part)
        if not loc:
            return
        uw = loc[0] if len(loc) == 1 else _fix(shapely.union_all(loc), grid)
        closing = shapely.buffer(shapely.buffer(uw, r, quad_segs=4), -r, quad_segs=4)
        gap = _op(shapely.difference, shapely.intersection(closing, box), uw, grid)
        if keep is not None and not gap.is_empty:
            gap = _op(shapely.intersection, gap, keep, grid)
        if gap.is_empty:
            return
        gi = shapely.union_all(by_owner.get(oi, []))
        gj = shapely.union_all(by_owner.get(oj, []))
        shapely.prepare(gi)
        shapely.prepare(gj)
        for q in c.explode_parts(gap):
            if q.geom_type != "Polygon" or (keep is None and c.area_km2(q) <= 1e-6) or q.area <= 0:
                continue
            if not (shapely.dwithin(gi, q, tol) and shapely.dwithin(gj, q, tol)):
                continue
            li, lj = _shared_len(q, gi, tol, True), _shared_len(q, gj, tol, True)
            if frags is not None:  # tile mode: pieces are joined across the tile edges first, one owner for the whole piece
                frags.append((q, li, lj))
                continue
            owner = oi if li >= lj else oj
            P.append(q)
            O.append(owner)
            touched.add(owner)
            rep["gap_parts"] += 1
            rep["gap_km2"] += c.area_km2(q)
            changed.add(owner)

    def active_tiles(pa, pb, win, size):
        """Tiles (ix, iy) of the window where the boundaries of both parts come close (within one tile): big parts are only worked on there."""
        def tiles_of(g):
            bnd = shapely.segmentize(shapely.boundary(_clip(g, win, grid)), size / 2)
            xy = shapely.get_coordinates(bnd)
            if not len(xy):
                return set()
            ix = np.floor((xy[:, 0] - win[0]) / size).astype(int)
            iy = np.floor((xy[:, 1] - win[1]) / size).astype(int)
            return set(zip(ix.tolist(), iy.tolist()))
        ta, tb = tiles_of(pa), tiles_of(pb)
        grown = {(x + dx, y + dy) for (x, y) in ta for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        return sorted(grown & tb)

    for ip, (a_, b_) in enumerate(pairs):
        _tick("sliver pairs", ip, len(pairs), t_sl)
        oi, oj = O[a_], O[b_]
        bi, bj = P[a_].bounds, P[b_].bounds
        win = (max(bi[0], bj[0]) - 2 * gap_width, max(bi[1], bj[1]) - 2 * gap_width,
               min(bi[2], bj[2]) + 2 * gap_width, min(bi[3], bj[3]) + 2 * gap_width)
        if win[0] >= win[2] or win[1] >= win[3]:
            continue
        area_win = (win[2] - win[0]) * (win[3] - win[1])
        if PROGRESS["log"] and area_win > 1.0:
            PROGRESS["log"](f"      sliver window {ip + 1}/{len(pairs)}: {win[2] - win[0]:.2f} x {win[3] - win[1]:.2f} deg")
        nv = int(shapely.get_num_coordinates(P[a_]) + shapely.get_num_coordinates(P[b_]))
        if nv > TILE_MODE_VERTICES and area_win > TILE_MODE_MIN_AREA_DEG2:
            # very big parts (PHL: 170-590 thousand vertices per island group): working on the whole window takes ~10 min per pair,
            # so only the tiles where both parts come close are processed (result: the same closing, tile by tile)
            size = TILE_DEG
            tl = active_tiles(P[a_], P[b_], win, size)
            if PROGRESS["log"]:
                PROGRESS["log"](f"      sliver pair {ip + 1}/{len(pairs)}: parts of {nv} vertices, tile mode: {len(tl)} active tile(s) of {size} deg")
            frags: list = []
            for t_i, (ix, iy) in enumerate(tl):
                _tick("sliver tiles", t_i, len(tl), t_sl)
                tb = (win[0] + ix * size, win[1] + iy * size, win[0] + (ix + 1) * size, win[1] + (iy + 1) * size)
                # tiles overlap by 2 gap widths: pieces of neighbouring tiles overlap, so they merge without hairline cracks at the tile edge
                kb = (tb[0] - 2 * gap_width, tb[1] - 2 * gap_width, tb[2] + 2 * gap_width, tb[3] + 2 * gap_width)
                wt = (kb[0] - 4 * gap_width, kb[1] - 4 * gap_width, kb[2] + 4 * gap_width, kb[3] + 4 * gap_width)
                process_window(wt, oi, oj, keep=shapely.box(*kb), frags=frags)
            if frags:
                comps = c.explode_parts(_fix(shapely.union_all([f[0] for f in frags]), grid))
                reps_pts = shapely.point_on_surface(np.array([f[0] for f in frags], dtype=object))
                for comp in comps:
                    if comp.geom_type != "Polygon" or comp.is_empty:
                        continue
                    shapely.prepare(comp)
                    inside = [k for k in range(len(frags)) if shapely.contains(comp, reps_pts[k]) or shapely.intersects(comp, reps_pts[k])]
                    li = sum(frags[k][1] for k in inside)
                    lj = sum(frags[k][2] for k in inside)
                    owner = oi if li >= lj else oj
                    P.append(comp)
                    O.append(owner)
                    touched.add(owner)
                    rep["gap_parts"] += 1
                    rep["gap_km2"] += c.area_km2(comp)
                    changed.add(owner)
            continue
        process_window(win, oi, oj)
    # 3. put the units together again (only units that were touched are re-unioned)
    by_unit: dict[int, list] = {}
    for k in range(len(P)):
        if P[k] is not None and not P[k].is_empty and O[k] in touched:
            by_unit.setdefault(O[k], []).append(P[k])
    for k in touched:
        ps = by_unit.get(k, [])
        if ps:
            G[k] = _fix(shapely.union_all(ps, grid_size=grid) if grid else shapely.union_all(ps), grid)
    rep["overlap_km2"] = round(rep["overlap_km2"], 4)
    rep["gap_km2"] = round(rep["gap_km2"], 4)
    rep["units_changed"] = sorted(changed)
    empty = [k for k in range(n) if G[k] is None or G[k].is_empty]
    if empty:
        raise c.BuildError(f"coverage cleaning: unit(s) {empty} became empty")
    if not overlaps_only:
        G = _renode(G, grid)
    elif grid:
        # rounding stage of clean=overlaps: snap-round the boundaries of the cluster together; faces covered by two units go to the unit
        # of the smaller code, faces covered by none (gaps) stay open. Overlaps that rounding made of nearly parallel long edges vanish here.
        G = _renode(G, grid, priority)
    return G, rep


def _renode(G, grid: Optional[float], priority: Optional[list] = None) -> list:
    """Make shared boundaries IDENTICAL vertex by vertex: node the boundaries of all units together, polygonize, give every face to
    the unit that covers it (faces covered by no unit are water or holes and are dropped). Needed because cleaning leaves vertices
    that lie on the middle of a segment of the neighbour; the coverage simplifier needs exactly matching edges."""
    lines = [shapely.boundary(g) for g in G]
    ngrid = grid or c.PRECISION_GRID
    noded = shapely.union_all(lines, grid_size=ngrid)
    faces = [f for f in shapely.get_parts(shapely.polygonize([noded])) if not f.is_empty]
    reps = shapely.point_on_surface(np.array(faces, dtype=object))
    tree = shapely.STRtree(G)
    pi, gi = tree.query(reps, predicate="intersects")
    owner: dict[int, int] = {}
    pr = priority if priority is not None else list(range(len(G)))
    for k, u in zip(pi, gi):  # a face covered by several units (an overlap) goes to the unit of the smallest priority number
        k, u = int(k), int(u)
        if k not in owner or (pr[u], u) < (pr[owner[k]], owner[k]):
            owner[k] = u
    by_unit: dict[int, list] = {}
    for k, u in owner.items():
        by_unit.setdefault(u, []).append(faces[k])
    out = []
    for u in range(len(G)):
        fs = by_unit.get(u)
        if not fs:
            raise c.BuildError(f"coverage re-noding: unit {u} got no face")
        g = fs[0] if len(fs) == 1 else shapely.union_all(fs, grid_size=ngrid)
        out.append(_fix(g, grid))
    return out


def coverage_needs_cleaning(geoms, gap_width: float = GAP_WIDTH_DEG) -> bool:
    arr = np.array(geoms, dtype=object)
    return not bool(shapely.coverage_is_valid(arr, gap_width=gap_width))


def simplify_coverage(ids, geoms, tol: float = SIMPLIFY_TOL_DEG) -> tuple[list, list[dict], dict]:
    """Coverage simplification with shared edges kept identical (GEOS coverage simplifier). Returns (geoms, per-unit report, summary).
    Per unit: area before/after, change in per cent, parts before/after, lost parts (less than LOST_PART_KEEP of the part is left).
    A unit that loses more than SIMPLIFY_LOSS_STOP of its area, or vanishes, stops the build."""
    if not hasattr(shapely, "coverage_simplify"):
        raise c.BuildError("shapely.coverage_simplify is missing (needs shapely >= 2.1 with GEOS >= 3.12); upgrade shapely: pip install -U shapely")
    arr = np.array(geoms, dtype=object)
    out = shapely.coverage_simplify(arr, tol, simplify_boundary=True)
    out = [_fix(g, None) for g in out]
    rows, stop = [], []
    for uid, a, b in zip(ids, geoms, out):
        if b is None or b.is_empty:
            raise c.BuildError(f"coverage simplification: unit {uid} vanished (tolerance {tol} deg). Stop.")
        ka, kb = c.area_km2(a), c.area_km2(b)
        pa, pb = [p for p in c.explode_parts(a) if p.area > 0], [p for p in c.explode_parts(b) if p.area > 0]
        tree = shapely.STRtree(pb)
        lost, lost_km2 = 0, 0.0
        for p in pa:
            cand = tree.query(p, predicate="intersects")
            inter = sum(shapely.intersection(p, pb[k]).area for k in cand) if len(cand) else 0.0
            if p.area > 0 and inter / p.area < LOST_PART_KEEP:
                lost += 1
                lost_km2 += c.area_km2(p)
        ch = (kb - ka) / ka if ka else 0.0
        rows.append(dict(unit_id=uid, area_before_km2=round(ka, 3), area_after_km2=round(kb, 3), change_pct=round(100 * ch, 4),
                         parts_before=len(pa), parts_after=len(pb), lost_parts=lost, lost_parts_km2=round(lost_km2, 4)))
        if abs(ch) > SIMPLIFY_LOSS_STOP:
            stop.append(f"{uid}: {100 * ch:+.2f} %")
    if stop:
        raise c.BuildError(f"coverage simplification: unit(s) change area by more than {SIMPLIFY_LOSS_STOP:.0%}: {stop}. Stop and ask [ARCH7].")
    arr_out = np.array(out, dtype=object)
    valid = bool(shapely.coverage_is_valid(arr_out, gap_width=0.0))
    inv_km, inv_units = 0.0, 0
    if not valid:  # how bad: length of the edges that do not match a neighbour (overlap or a vertex off the shared edge)
        for ge in shapely.coverage_invalid_edges(arr_out, gap_width=0.0):
            if ge is not None and not ge.is_empty:
                inv_units += 1
                inv_km += float(shapely.length(ge)) * 111.0
    summary = dict(method="shapely.coverage_simplify (GEOS coverage simplifier, simplify_boundary=True)", tolerance_deg=tol,
                   max_abs_change_pct=max(abs(r["change_pct"]) for r in rows), total_lost_parts=sum(r["lost_parts"] for r in rows),
                   units_with_lost_parts=sum(1 for r in rows if r["lost_parts"]), coverage_valid_after=valid,
                   invalid_edges_km=round(inv_km, 2), units_with_invalid_edges=inv_units)
    return out, rows, summary


def round_coverage(geoms, decimals: int, clean: str = "full", priority: Optional[list] = None) -> tuple[list, dict]:
    """Topology-preserving rounding of a whole coverage to `decimals` decimals: every vertex is snapped to the grid, then the
    coverage is cleaned again with every operation on that grid (overlaps and slivers that the snapping made are handed over)."""
    grid = 10.0 ** -decimals
    snapped = []
    n_invalid_in = 0
    for g in geoms:
        if not g.is_valid:  # set_precision (valid_output) needs a valid input
            n_invalid_in += 1
            g = c._to_polygonal(shapely.make_valid(g))
        try:
            s = shapely.set_precision(g, grid)
        except shapely.errors.GEOSException:
            s = shapely.set_precision(g, grid, mode="pointwise")
        s = shapely.transform(s, lambda a: np.round(a, decimals))
        if not s.is_valid:
            s = shapely.make_valid(s)
        snapped.append(c._to_polygonal(s))
    if clean == "no":  # table flag clean=no: nothing is cleaned after the snapping; the validator tolerances cover the rest
        G, rep = list(snapped), {"overlap_pairs": 0, "overlap_km2": 0.0, "gap_parts": 0, "gap_km2": 0.0, "units_changed": [], "mode": "none"}
    elif clean == "overlaps":
        G, rep = clean_coverage(snapped, grid=grid, overlaps_only=True, priority=priority)
    else:
        G, rep = clean_coverage(snapped, grid=grid)
    G = [c._to_polygonal(shapely.transform(g, lambda a: np.round(a, decimals))) for g in G]
    bad = [k for k, g in enumerate(G) if g is None or g.is_empty or not g.is_valid]
    repaired = []
    for k in list(bad):
        g = G[k]
        if g is None or g.is_empty:
            continue
        a0 = c.area_km2(g)
        try:
            r = c._to_polygonal(shapely.make_valid(g))
            r = c._to_polygonal(shapely.transform(shapely.set_precision(r, grid), lambda a: np.round(a, decimals)))
        except shapely.errors.GEOSException:
            continue
        if r is not None and not r.is_empty and r.is_valid:
            G[k] = r
            repaired.append(dict(index=k, reason=shapely.is_valid_reason(g), area_before_km2=round(a0, 6), area_after_km2=round(c.area_km2(r), 6)))
            bad.remove(k)
    rep["repaired_after_rounding"] = repaired
    if repaired:
        c_log = PROGRESS["log"]
        if c_log:
            c_log(f"      rounding: {len(repaired)} unit(s) repaired after rounding (make_valid + grid): {repaired}")
    if bad:
        why = {k: ("empty" if G[k] is None or G[k].is_empty else shapely.is_valid_reason(G[k])) for k in bad}
        raise c.BuildError(f"rounding to {decimals} decimals: unit(s) {bad} empty or invalid: {why}")
    rep["decimals"] = decimals
    rep["invalid_inputs_repaired"] = n_invalid_in
    rep["max_decimals_after"] = max(max_decimals(g) for g in G)
    if rep["max_decimals_after"] > decimals:
        raise c.BuildError(f"rounding to {decimals} decimals left coordinates with {rep['max_decimals_after']} decimals")
    return G, rep


# --------------------------------------------------------------------------
# Conforming (display geometry)
# --------------------------------------------------------------------------

def border_corridor(country_poly, neighbours_union, deg: float = CORRIDOR_DEG):
    """Corridor around the part of the country's boundary that lies on a neighbour (land border). Empty geometry if none."""
    if neighbours_union is None or neighbours_union.is_empty:
        return shapely.Polygon()
    window = shapely.box(*country_poly.bounds).buffer(0.05)
    n_loc = c.clean(shapely.intersection(neighbours_union, window))
    if n_loc.is_empty:
        return shapely.Polygon()
    shared = shapely.intersection(country_poly.boundary, shapely.buffer(n_loc, c.BOUNDARY_TOUCH_TOL_DEG, quad_segs=1))
    if shared.is_empty:
        return shapely.Polygon()
    return shapely.buffer(shared, deg)


def land_gap_parts(country_poly, units_union, corridor, lakes_union, mask=None):
    """Parts of (ADM0 - units - mask) inside the border corridor that are not water. `mask` = neighbours' ADM0 and published ADM1
    (what the neighbours already show inside this ADM0 is not a gap of ours)."""
    if corridor.is_empty:
        return [], 0.0
    gap = c.clean(shapely.difference(country_poly, units_union))
    if mask is not None and not mask.is_empty and not gap.is_empty:
        gap = c.clean(shapely.difference(gap, mask))
    gap = c.clean(shapely.intersection(gap, corridor)) if not gap.is_empty else gap
    parts = [p for p in c.explode_parts(gap) if c.area_km2(p) > 1e-6]
    shapely.prepare(lakes_union)
    land = []
    for p in parts:
        if p.area > 0 and shapely.intersection(p, lakes_union).area / p.area >= c.WATER_GAP_FRACTION:
            continue
        land.append(p)
    return land, sum(c.area_km2(p) for p in land)


def neighbour_masks(adm0_geom: dict, published_adm1, nb: list[str], country_poly):
    """-> (adm0_union, mask). adm0_union = ADM0 of the neighbours (defines the land border and the corridor); mask = that union plus
    the already published ADM1 of the neighbours near this country (ARCH7 D2). Published ADM1 = ADM1 of v0.2.0 (not national)."""
    if not nb:
        return shapely.Polygon(), shapely.Polygon()
    adm0_u = c.union_clean([adm0_geom[x] for x in nb])
    mask = adm0_u
    if published_adm1 is not None and len(published_adm1):
        sub = published_adm1[published_adm1["iso3"].isin(nb)]
        if len(sub):
            window = shapely.box(*country_poly.bounds).buffer(0.5)
            tree = shapely.STRtree(sub.geometry.values)
            idx = tree.query(window, predicate="intersects")
            if len(idx):
                parts = [c.clean(shapely.intersection(sub.geometry.values[i], window)) for i in idx]
                a1 = c.union_clean([p for p in parts if not p.is_empty])
                mask = c.union_clean([adm0_u, a1])
    return adm0_u, mask


def conform_country(units: gpd.GeoDataFrame, country_poly, neighbours_union, lakes_union, sea: str,
                    logger: c.BuildLogger, iso3: str, mask=None) -> tuple[gpd.GeoDataFrame, dict]:
    """Display geometry of one country. `units` has unit_id and geometry (EPSG:4326, cleaned). neighbours_union = ADM0 of the
    neighbours (border, corridor); mask = that plus the published ADM1 of the neighbours (what is removed and not refilled)."""
    if mask is None:
        mask = neighbours_union
    rep: dict = {"iso3": iso3, "sea": sea}
    raw_union = c.clean(unary_union(units.geometry.values))
    raw_km2 = c.area_km2(raw_union)
    outside = c.area_km2(shapely.difference(raw_union, country_poly))
    rep["national_km2"] = round(raw_km2, 1)
    rep["outside_adm0_km2_before"] = round(outside, 1)
    rep["outside_adm0_share_before"] = round(outside / raw_km2, 4) if raw_km2 else None
    if sea != "clip" and raw_km2 and outside / raw_km2 > OUTSIDE_STOP_SHARE:
        raise c.BuildError(f"{iso3}: {outside / raw_km2:.1%} of the national polygons lie outside the ADM0 polygon; the source "
                           f"probably includes sea. Set sea=clip in national_sources_v030.csv (as HKG) -- stop and ask.")
    has_nb = neighbours_union is not None and not neighbours_union.is_empty
    out = units.copy()
    if has_nb:
        out = c.remove_encroachment(out, mask, logger, "unit_id")
    if sea == "clip":
        out = c.clip_to_country(out, country_poly, logger, "unit_id")
    corridor = border_corridor(country_poly, neighbours_union) if has_nb else shapely.Polygon()
    filled0, resid = 0.0, 0.0
    for it in range(1, 6):
        uni = c.clean(unary_union(out.geometry.values))
        land, land_km2 = land_gap_parts(country_poly, uni, corridor, lakes_union, mask)
        if it == 1:
            filled0 = land_km2
        resid = land_km2
        if land_km2 <= LAND_RESIDUAL_TOL_KM2 or not land:
            break
        out = c.assign_land_gaps(out, land, logger, "unit_id")
    rep.update(land_gap_initial_km2=round(filled0, 4), land_gap_residual_km2=round(resid, 4), iterations=it)
    empty = out.loc[out.geometry.isna() | out.geometry.is_empty, "unit_id"].tolist()
    if empty:
        raise c.BuildError(f"{iso3}: unit(s) empty after conforming: {empty}")
    uni = c.clean(unary_union(out.geometry.values))
    rep["display_km2"] = round(c.area_km2(uni), 1)
    rep["outside_adm0_km2_after"] = round(c.area_km2(shapely.difference(uni, country_poly)), 1)
    logger.add(step="national_conform", **rep)
    return out, rep


def measure_residuals(units_geoms, country_poly, neighbours_union, lakes_union, mask=None) -> dict:
    """Independent measure for validation: encroachment on the neighbours (ADM0, and published ADM1 when `mask` is given) and land
    gap in the border corridor."""
    if mask is None:
        mask = neighbours_union
    uni = c.union_clean(list(units_geoms))
    has_nb = mask is not None and not mask.is_empty
    encroach = c.area_km2(shapely.intersection(uni, mask)) if has_nb else 0.0
    corridor = border_corridor(country_poly, neighbours_union) if (neighbours_union is not None and not neighbours_union.is_empty) else shapely.Polygon()
    land, land_km2 = land_gap_parts(country_poly, uni, corridor, lakes_union, mask)
    return {"encroachment_km2": round(encroach, 4), "land_gap_km2": round(land_km2, 4), "n_land_fragments": len(land)}


# --------------------------------------------------------------------------
# Text found in the saved pages (IDN rights search, KOR creation date) -- ARCH7 r5 items 1 and 11
# --------------------------------------------------------------------------

RIGHTS_WORDS = ["Hak Cipta", "©", "Copyright", "dilindungi", "lisensi"]
_TEXT_EXT = {".mhtml", ".mht", ".html", ".htm", ".xml", ".json", ".pjson", ".txt", ".pdf", ".md", ".srcinfo"}
_SKIP_EXT = {".zip", ".geojson", ".gpkg", ".shp", ".dbf", ".shx", ".prj", ".cpg", ".gdb", ".7z", ".gz", ".parquet", ".tif", ".png", ".jpg"}
_MAX_TEXT_BYTES = 25 * 1024 * 1024


def _strip_html(t: str) -> str:
    import html as _html
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t))


def _json_values_text(raw: str) -> str:
    """Text of the VALUES of a JSON document, one 'key: value' line each: the name of a field ('copyrightText' of every ArcGIS layer)
    is not a reservation of rights, its content may be."""
    import json as _json
    try:
        doc = _json.loads(raw)
    except ValueError:
        return raw
    out = []

    def walk(x, key=""):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, str(k))
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif x is not None and str(x).strip():
            out.append(str(x))
    walk(doc)
    return "\n".join(out)


def _json_credit_fields(raw: str) -> dict:
    """Fields of a JSON description that carry a credit or a licence ('copyrightText', 'licenseInfo', 'credit', 'attribution'): reported as found."""
    import json as _json
    try:
        doc = _json.loads(raw)
    except ValueError:
        return {}
    out = {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if re.search(r"copyright|licen[cs]e|credit|attribution|rights", str(k), re.I) and not isinstance(v, (dict, list)):
                    out[str(k)] = v
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    return out


def extract_text(path: Path) -> str:
    """Plain text of a saved page / XML / JSON / PDF (.mhtml: every text part decoded with its own charset)."""
    ext = path.suffix.lower()
    data = path.read_bytes()
    if ext == ".pdf":
        import pypdf
        r = pypdf.PdfReader(str(path))
        return "\n".join((pg.extract_text() or "") for pg in r.pages)
    if ext in (".mhtml", ".mht") or data[:300].lstrip().lower().startswith((b"from:", b"mime-version", b"subject:", b"date:")):
        import email
        from email import policy
        msg = email.message_from_bytes(data, policy=policy.default)
        out = []
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                try:
                    txt = part.get_content()
                except Exception:  # noqa: BLE001
                    txt = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
                out.append(_strip_html(txt) if part.get_content_subtype() in ("html", "xml") else txt)
        return "\n".join(out)
    for enc in ("utf-8", "utf-16", "cp1252"):
        try:
            txt = data.decode(enc)
            if ext in (".json", ".pjson"):
                txt = _json_values_text(txt)
            break
        except UnicodeDecodeError:
            continue
    else:
        txt = data.decode("utf-8", "replace")
    return _strip_html(txt) if ext in (".html", ".htm", ".xml") else txt


def _country_files(root: Path, iso3: str):
    folder = root / iso3.lower()
    if not folder.exists():
        folder = root / iso3.upper()
    out = []
    if folder.exists():
        for q in sorted(folder.rglob("*")):
            if not q.is_file() or any(x.startswith("_") for x in q.relative_to(folder).parts):
                continue
            if q.suffix.lower() in _SKIP_EXT or q.suffix.lower() not in _TEXT_EXT or q.stat().st_size > _MAX_TEXT_BYTES:
                continue
            out.append(q)
    return out, folder


def rights_search(root: Path, iso3: str = "IDN", words=RIGHTS_WORDS) -> dict:
    """ARCH7 r5 item 11: search the saved BIG pages, the ISO 19115-3 XML and the JSON description of the REST layer for a reservation
    of rights. The text of the law itself (UU 28/2014: it contains the words by nature) is listed and left out. Found = a hit in a file
    that is not the law -> IDN is not released."""
    files, folder = _country_files(root, iso3)
    searched, hits, excluded, unreadable, credit_fields = [], [], [], [], {}
    empty_pages: list[str] = []
    for q in files:
        try:
            txt = extract_text(q)
        except Exception as e:  # noqa: BLE001
            unreadable.append(f"{q.name}: {type(e).__name__}")
            continue
        low = txt.lower()
        is_law = ("28 tahun 2014" in low and "hak cipta" in low) or "pasal 43" in low
        kind = {".xml": "xml", ".json": "json", ".pjson": "json", ".pdf": "pdf"}.get(q.suffix.lower(), "page")
        head = low[:4000]
        is_reg = kind == "pdf" and ("peraturan" in head or "undang-undang" in head or "keputusan" in head or "peraturan" in q.name.lower())
        if is_law or is_reg:
            excluded.append(dict(file=q.name, kind=kind, reason=("text of the law UU 28/2014" if is_law else
                              "regulation / legal text (not a BIG item description); contains the words by nature")))
            continue
        searched.append(dict(file=q.name, kind=kind, chars=len(txt)))
        if kind == "page" and len(txt.strip()) < 200:
            empty_pages.append(q.name)
        if kind == "json":
            try:
                fields = _json_credit_fields(q.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                fields = {}
            if fields:
                credit_fields[q.name] = fields
        for w in words:
            wl = w.lower()
            start, n = 0, 0
            while n < 3:
                k = low.find(wl, start)
                if k < 0:
                    break
                hits.append(dict(file=q.name, word=w, context=txt[max(0, k - 70):k + len(w) + 70].replace("\n", " ")))
                start, n = k + len(wl), n + 1
    kinds = sorted({x["kind"] for x in searched})
    missing = [k for k in ("xml", "json") if k not in kinds]
    line = (f"{iso3} rights search: words {words}; folder {folder}; searched {len(searched)} file(s) "
            f"({', '.join(f'{k}: ' + str(sum(1 for x in searched if x['kind'] == k)) for k in kinds) or 'none'}); "
            f"left out as the law text: {len(excluded)}; unreadable: {len(unreadable)}; found: {len(hits)} hit(s)"
            + (f"; credit/licence fields of the layer JSON: {credit_fields}" if credit_fields else "")
            + (f"; NOT in the folder: {', '.join(missing)}" if missing else "")
            + (f"; EMPTY pages (no text, not searched): {', '.join(empty_pages)}" if empty_pages else ""))
    # complete = the ISO 19115 XML of the item was searched and nothing was unreadable; the layer JSON and the empty JS-shell page are
    # reported in the line (not saved) but do not block
    complete = ('xml' in kinds) and not unreadable
    line += f"; search complete: {complete}"
    return dict(complete=complete, empty_pages=empty_pages, line=line, found=bool(hits), n_hits=len(hits), hits=hits[:40], searched=searched, excluded=excluded,
                unreadable=unreadable, missing_kinds=missing, words=list(words), json_credit_fields=credit_fields)


def text_proof(root: Path, iso3: str, rx: str) -> dict:
    """Is the regex found in the text of a page saved in the country folder? (the legal act behind a regroup rule). Read-only."""
    files, folder = _country_files(root, iso3)
    pat = re.compile(rx, re.I | re.S)
    searched, unreadable = [], []
    for q in files:
        try:
            txt = re.sub(r"\s+", " ", extract_text(q))
        except Exception as e:  # noqa: BLE001
            unreadable.append(f"{q.name}: {type(e).__name__}")
            continue
        searched.append(q.name)
        m = pat.search(txt)
        if m:
            ctx = txt[max(0, m.start() - 60):m.end() + 60]
            return dict(found=True, file=q.name, sha256=c.sha256_file(q),
                        line=f"found in {q.name} (sha256 {c.sha256_file(q)[:16]}...): ...{ctx}...")
    return dict(found=False, line=f"folder {folder}; searched {len(searched)} file(s) {searched[:8]}; unreadable {unreadable[:5]}; pattern {rx!r}")


_DATE_RX = r"(20\d\d)\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[.일]?"


def law_creation_date(root: Path, iso3: str, law_phrase: str = "통합특별시 설치", law_no: str = "21446") -> dict:
    """ARCH7 r5 item 1 (KOR): the date of creation of the merged unit, taken by code from the 부칙 (supplementary provisions) of the
    saved law. A 부칙 block counts only if its header names the law itself ('부칙 <법률 제21446호 ...>'): the blocks of amending laws
    follow in the same page and have their own dates. Date = the first '<date>부터 시행' in such a block. None = the saved pages do not
    hold it (then the 연혁 page of the law is needed). All 부칙 blocks found are listed with their context."""
    files, folder = _country_files(root, iso3)
    cands, own, searched = [], [], []
    for q in files:
        if q.suffix.lower() not in (".pdf", ".mhtml", ".mht", ".html", ".htm", ".txt"):
            continue
        try:
            txt = extract_text(q)
        except Exception:  # noqa: BLE001
            continue
        if law_phrase not in txt:
            continue
        searched.append(q.name)
        # the page of the ORIGINAL (제정) text of the law: '[시행 <date>] [법률 제21446호, <promulgation>, 제정]' in its header
        orig = re.search(r"\[시행\s*" + _DATE_RX + r"\s*\]\s*\[법률\s*제" + law_no + r"호\s*,\s*" + _DATE_RX + r"\s*,\s*제정\s*\]", txt)
        promulgated = (f"{int(orig.group(4)):04d}-{int(orig.group(5)):02d}-{int(orig.group(6)):02d}" if orig else None)
        in_force_hdr = (f"{int(orig.group(1)):04d}-{int(orig.group(2)):02d}-{int(orig.group(3)):02d}" if orig else None)
        for m in re.finditer("부칙", txt):
            seg = txt[m.start():m.start() + 400]
            head = seg[:80]
            d = re.search(_DATE_RX + r"\s*부터\s*시행", seg)
            starts_art1 = bool(re.match(r"부칙\s*(<[^>]*>)?\s*제1조\s*\(시행일\)\s*이 법은", seg))
            item = dict(file=q.name, header=head.replace("\n", " "), context=seg[:160].replace("\n", " "),
                        date=(f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else None),
                        names_the_law=(f"제{law_no}호" in head) or (bool(orig) and starts_art1),
                        promulgated=promulgated, in_force_in_header=in_force_hdr)
            cands.append(item)
            if item["names_the_law"] and item["date"]:
                own.append(item)
    best = own[0] if own else None
    return dict(date=best["date"] if best else None, file=best["file"] if best else None,
                promulgated=best.get("promulgated") if best else None,
                header_agrees=bool(best and best.get("in_force_in_header") == best["date"]),
                candidates=cands[:12], searched_files=searched, folder=str(folder),
                note=(f"date taken from the 부칙 of the saved law (law no. {law_no})" if best else
                      f"no 부칙 block of the law itself (제{law_no}호) with a date in the saved pages (the 부칙 found belong to amending laws); "
                      "save the original (제정) text of the law from law.go.kr (연혁) to the KOR folder as .txt or .pdf"))


# --------------------------------------------------------------------------
# Whole build
# --------------------------------------------------------------------------

def build_national_adm1(root: Path, table_path: Path, names_path: Path, adm0: gpd.GeoDataFrame, lakes_union, manifest: dict,
                        registry: Optional[pd.DataFrame], logger: c.BuildLogger, log=print, only: Optional[list[str]] = None,
                        published_adm1: Optional[gpd.GeoDataFrame] = None, cache_dir: Optional[Path] = None):
    """-> (display ADM1 GeoDataFrame in the layout of build_plan_adm1, {iso3: analysis GeoDataFrame}, report dict, meta sources, review rows,
    extras dict). published_adm1 = the ADM1 of v0.2.0 built in this run (USA, NOR, FRA, GBR, plan countries): subtracted from the national countries
    along their land borders (ARCH7 D2)."""
    table = load_table(table_path)
    names_tbl = load_names(names_path)
    tbd = table[table["url"].str.startswith("TBD")]
    if len(tbd):
        raise c.BuildError(f"national_sources_v030.csv: url of {tbd['iso3'].tolist()} is not filled in ({tbd['url'].iloc[0]!r}). Stop.")
    cldr = Cldr(manifest)
    PROGRESS["log"] = log  # progress lines of the long steps (cleaning, rounding) go to the build log
    adm0_geom = dict(zip(adm0["unit_id"], adm0.geometry))
    isos = [i for i in table["iso3"].drop_duplicates().tolist() if not only or i in only]
    display_rows, analysis, report, sources, review_all = [], {}, {}, [], []
    extras: dict = {}
    if "IDN" in isos:
        rs = rights_search(root, "IDN")
        log("  " + rs["line"])
        extras["idn_rights_search"] = rs
        if rs["found"]:
            raise c.BuildError("IDN: words of a reservation of rights found in the saved BIG files -- IDN is not released (ARCH7 r5 item 11). "
                               f"Hits: {rs['hits'][:6]}. Rebuild with --exclude-countries IDN or ask [ARCH7].")
    for iso3 in isos:
        rows = table[table["iso3"] == iso3]
        t0 = time.time()
        log(f"national ADM1 {iso3}: reading {len(rows)} part(s)...")
        units, infos = read_country(root, rows)
        for i_ in infos:
            for r_ in i_.get("regroup", []):
                log(f"  regroup {r_['rule']!r}: {r_['rows']} row(s) {r_['names']} from {r_['from_groups']} to {r_['to']}"
                    + (f"; proof {r_['proof']}" if r_["proof"] else ""))
                log(f"    groups after the regrouping: {r_['groups_after']}")
            for r_ in i_.get("regroup_skipped", []):
                log(f"  WARNING regroup rule NOT applied (source file shown as it is): {r_['rule']!r}; {r_['reason']}")
        decimals = int(rows["coord_decimals"].iloc[0] or 0) if rows["coord_decimals"].iloc[0] else 0
        units, review = resolve_names(iso3, units, rows, names_tbl, cldr)
        review_all.extend(review)
        # acceptance points ("lon lat=>unit_id")
        for _, r in rows.iterrows():
            if r["accept_points"]:
                for item in r["accept_points"].split(";"):
                    xy, uid = item.split("=>")
                    lon, lat = (float(x) for x in xy.split())
                    inside = units.loc[units.geometry.apply(lambda g: g.contains(shapely.Point(lon, lat))), "unit_id"].tolist()
                    if inside != [uid.strip()]:
                        raise c.BuildError(f"{iso3}: point {lon} {lat} is in {inside}, expected [{uid.strip()!r}]")
                    log(f"  acceptance point {lon} {lat}: in {uid.strip()}")
        # analysis geometry: official polygons as they are (IDN: rounded to coord_decimals, unit by unit, as published)
        a_geom = list(units.geometry.values)
        a = gpd.GeoDataFrame({"unit_id": units["unit_id"].values, "iso3": iso3, "level": "ADM1", "parent_id": iso3,
                              "geometry": a_geom}, crs=c.CRS_WGS84)
        if decimals:
            a["geometry"] = [round_geom(g, decimals) for g in a.geometry.values]
        vintage = sorted({v for v in units["vintage"]})[-1]
        tag = rows["tag"].iloc[0] or "national"
        analysis[iso3] = (a, f"{iso3}_adm1_{tag}_{re.sub(r'[^0-9]', '', vintage)}.parquet")
        ids = units["unit_id"].tolist()
        official = {u: g for u, g in zip(ids, units.geometry.values)}
        # ---- display geometry: clean -> simplify -> conform -> round (table flags clean= / simplify=, ARCH7 18.11)
        clean_mode = (rows["clean"].iloc[0] or "full").strip().lower()
        simplify_on = (rows["simplify"].iloc[0] or "yes").strip().lower() != "no"
        t1 = time.time()
        geoms = list(units.geometry.values)
        crep = None
        n_vert = sum(shapely.get_num_coordinates(g) for g in geoms)
        log(f"  {len(geoms)} units read, {n_vert} vertices ({time.time() - t0:.0f}s since start of country); clean={clean_mode}, simplify={'yes' if simplify_on else 'no'}")

        def _code_key(cd):
            cd = str(cd).strip()
            return (0, int(cd), "") if cd.isdigit() else (1, 0, cd)
        order = sorted(range(len(ids)), key=lambda k: _code_key(units["code"].iloc[k]))
        rank = [0] * len(ids)
        for r_, k_ in enumerate(order):
            rank[k_] = r_
        prio_by_id = {ids[k]: rank[k] for k in range(len(ids))}
        # checkpoint of the long step (clean + simplify): reused only if the input geometries and the parameters are identical
        ck_key = hashlib.sha256(b"".join(shapely.to_wkb(geoms)) + repr((GAP_WIDTH_DEG, SIMPLIFY_TOL_DEG, TINY_OVERLAP_KM2, decimals, ids,
                                                                        clean_mode, simplify_on, "v2")).encode()).hexdigest()[:20]
        big = iso3 in ("IDN", "PHL", "THA", "VNM") or n_vert > 3_000_000
        ck_path = cache_dir / f"{iso3}_clean_simplify_{ck_key}.pkl" if cache_dir and big else None
        loaded = None
        if ck_path is not None and ck_path.exists():
            try:
                loaded = pickle.loads(ck_path.read_bytes())
                log(f"  checkpoint {ck_path.name} found: cleaning and simplification are taken from it")
            except Exception as e:  # noqa: BLE001
                log(f"  checkpoint {ck_path.name} unreadable ({type(e).__name__}: {e}); recomputing")
        if loaded is not None:
            geoms = list(shapely.from_wkb(loaded["wkb"]))
            crep, srows, ssum = loaded["crep"], loaded["srows"], loaded["ssum"]
            log(f"  [checkpoint] cleaned: {(crep or {}).get('overlap_pairs')} overlapping pair(s), {(crep or {}).get('gap_parts')} sliver(s); "
                f"simplified: max area change {ssum['max_abs_change_pct']} %")
        else:
            if clean_mode == "no":
                crep = {"mode": "none (clean=no)", "overlap_pairs": 0, "overlap_km2": 0.0, "gap_parts": 0, "gap_km2": 0.0, "units_changed": []}
                log("  coverage not cleaned (clean=no)")
            elif clean_mode == "overlaps":
                geoms, crep = clean_coverage(geoms, overlaps_only=True, priority=rank)
                log(f"  overlaps taken out (clean=overlaps; the part stays with the smaller code): {crep['overlap_pairs']} overlapping pair(s) "
                    f"({crep['overlap_km2']} km2), {len(crep['units_changed'])} unit(s) changed; gaps not closed ({time.time() - t1:.0f}s)")
            elif decimals or coverage_needs_cleaning(geoms):
                geoms, crep = clean_coverage(geoms)
                log(f"  coverage cleaned: {crep['overlap_pairs']} overlapping pair(s) ({crep['overlap_km2']} km2), "
                    f"{crep['gap_parts']} sliver(s) closed ({crep['gap_km2']} km2), {len(crep['units_changed'])} unit(s) changed")
            else:
                log("  coverage valid: not cleaned")
            if simplify_on:
                geoms, srows, ssum = simplify_coverage(ids, geoms, SIMPLIFY_TOL_DEG)
            else:
                srows = []
                for uid, g in zip(ids, geoms):
                    ps = [q for q in c.explode_parts(g) if q.area > 0]
                    srows.append(dict(unit_id=uid, area_before_km2=round(c.area_km2(g), 3), area_after_km2=round(c.area_km2(g), 3), change_pct=0.0,
                                      parts_before=len(ps), parts_after=len(ps), lost_parts=0, lost_parts_km2=0.0))
                ssum = dict(method="none (simplify=no)", skipped=True, tolerance_deg=None, max_abs_change_pct=0.0, total_lost_parts=0,
                            units_with_lost_parts=0, coverage_valid_after=None, invalid_edges_km=0.0, units_with_invalid_edges=0)
            if ck_path is not None:
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    tmp = ck_path.with_suffix(".tmp")
                    tmp.write_bytes(pickle.dumps({"wkb": list(shapely.to_wkb(np.array(geoms, dtype=object))), "crep": crep, "srows": srows, "ssum": ssum}))
                    tmp.replace(ck_path)
                    log(f"  checkpoint written: {ck_path} ({ck_path.stat().st_size // 1024} KB)")
                except Exception as e:  # noqa: BLE001
                    log(f"  checkpoint not written ({type(e).__name__}: {e})")
        if ssum.get("skipped"):
            log("  not simplified (simplify=no)")
        else:
            log(f"  simplified (tolerance {SIMPLIFY_TOL_DEG} deg): max area change {ssum['max_abs_change_pct']} %, lost parts {ssum['total_lost_parts']} "
                f"in {ssum['units_with_lost_parts']} unit(s), coverage valid after: {ssum['coverage_valid_after']} "
                f"(invalid edges {ssum['invalid_edges_km']} km in {ssum['units_with_invalid_edges']} unit(s)) ({time.time() - t1:.0f}s)")
        nb = [x for x in rows["neighbors"].iloc[0].split(";") if x]
        absent = [x for x in nb if x not in adm0_geom]
        if absent:
            raise c.BuildError(f"{iso3}: neighbour(s) {absent} are not ADM0 units")
        nb_adm0, mask = neighbour_masks(adm0_geom, published_adm1, nb, adm0_geom[iso3])
        # second checkpoint (IDN): the whole display geometry after conforming and rounding; the final build takes IDN from it
        fk_path = None
        if cache_dir is not None and iso3 == "IDN":
            fk = hashlib.sha256((ck_key + hashlib.sha256(shapely.to_wkb(adm0_geom[iso3])).hexdigest()
                                 + hashlib.sha256(shapely.to_wkb(nb_adm0 if nb_adm0 is not None else shapely.Polygon())).hexdigest()
                                 + hashlib.sha256(shapely.to_wkb(mask if mask is not None else shapely.Polygon())).hexdigest()
                                 + repr((rows["sea"].iloc[0], decimals, clean_mode, "final-v1"))).encode()).hexdigest()[:20]
            fk_path = cache_dir / f"{iso3}_final_{fk}.pkl"
        disp = rep = rrep = None
        if fk_path is not None and fk_path.exists():
            try:
                fl = pickle.loads(fk_path.read_bytes())
                disp = gpd.GeoDataFrame({"unit_id": fl["ids"], "geometry": list(shapely.from_wkb(fl["wkb"]))}, crs=c.CRS_WGS84)
                rep, rrep = fl["rep"], fl["rrep"]
                logger.add(step="national_conform", **{k: v for k, v in rep.items() if isinstance(v, (int, float, str, type(None)))})
                log(f"  final checkpoint {fk_path.name} found: conforming and rounding are taken from it")
            except Exception as e:  # noqa: BLE001
                disp = None
                log(f"  final checkpoint {fk_path.name} unreadable ({type(e).__name__}: {e}); recomputing")
        if disp is None:
            log(f"  conforming to the neighbours ({time.time() - t0:.0f}s since start of country)...")
            simp_gdf = gpd.GeoDataFrame({"unit_id": ids, "geometry": geoms}, crs=c.CRS_WGS84)
            disp, rep = conform_country(simp_gdf, adm0_geom[iso3], nb_adm0, lakes_union, rows["sea"].iloc[0] or "none", logger, iso3, mask=mask)
            rrep = None
            if decimals:
                log(f"  rounding to {decimals} decimals ({time.time() - t0:.0f}s since start of country)...")
                disp_ids = disp["unit_id"].tolist()
                G, rrep = round_coverage(list(disp.geometry.values), decimals, clean=clean_mode,
                                         priority=[prio_by_id[u] for u in disp_ids])
                disp = gpd.GeoDataFrame({"unit_id": disp_ids, "geometry": G}, crs=c.CRS_WGS84)
                log(f"  rounded to {decimals} decimals: {rrep['overlap_pairs']} overlapping pair(s) taken out, {rrep['gap_parts']} sliver(s) closed after snapping")
            if clean_mode != "full":
                # what the light cleaning leaves (ARCH7 18.11 item 3): holes inside the union of the units and overlaps after rounding
                t2 = time.time()
                uni_all = shapely.union_all(list(disp.geometry.values))
                holes = [shapely.Polygon(rg) for pg in c.explode_parts(uni_all) if pg.geom_type == "Polygon" for rg in pg.interiors]
                hk = [c.area_km2(h) for h in holes]
                ovl = c.pairwise_overlaps(disp.reset_index(drop=True), tol_km2=1e-6)
                rep["inner_gaps"] = dict(what="holes inside the union of the units (gaps enclosed by the units; lake cut-outs of the source count too)",
                                         n=len(hk), km2=round(sum(hk), 4), n_below_1_km2=sum(1 for x in hk if x < 1.0),
                                         km2_below_1_km2=round(sum(x for x in hk if x < 1.0), 4), largest_km2=round(max(hk), 4) if hk else 0.0)
                rep["overlaps_after_rounding"] = dict(n_pairs=len(ovl), km2=round(sum(o["overlap_km2"] for o in ovl), 4),
                                                      largest_km2=max((o["overlap_km2"] for o in ovl), default=0.0), pairs=ovl[:20])
                log(f"  after the light cleaning: {rep['inner_gaps']['n']} hole(s) inside the union, {rep['inner_gaps']['km2']} km2 "
                    f"({rep['inner_gaps']['km2_below_1_km2']} km2 in holes below 1 km2); overlaps left after rounding: {rep['overlaps_after_rounding']['n_pairs']} pair(s), "
                    f"{rep['overlaps_after_rounding']['km2']} km2 ({time.time() - t2:.0f}s)")
            if fk_path is not None:
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    tmp = fk_path.with_suffix(".tmp")
                    tmp.write_bytes(pickle.dumps({"ids": disp["unit_id"].tolist(), "wkb": list(shapely.to_wkb(np.array(list(disp.geometry.values), dtype=object))),
                                                  "rep": rep, "rrep": rrep}))
                    tmp.replace(fk_path)
                    log(f"  final checkpoint written: {fk_path} ({fk_path.stat().st_size // 1024} KB)")
                except Exception as e:  # noqa: BLE001
                    log(f"  final checkpoint not written ({type(e).__name__}: {e})")
        disp = disp.set_index("unit_id")
        # per-unit report: official -> display
        sdict = {r["unit_id"]: r for r in srows}
        unit_rep = []
        for uid in ids:
            ka = c.area_km2(official[uid])
            kd = c.area_km2(disp.at[uid, "geometry"])
            r_ = dict(sdict[uid])
            r_.update(area_official_km2=round(ka, 3), area_display_km2=round(kd, 3),
                      change_official_to_display_pct=round(100 * (kd - ka) / ka, 4) if ka else None,
                      parts_display=len([p for p in c.explode_parts(disp.at[uid, "geometry"]) if p.area > 0]))
            unit_rep.append(r_)
        reg = registry[(registry["iso3"] == iso3) & (registry["level"] == "ADM1")] if registry is not None else None
        published = reg is not None and bool(len(reg)) and str(reg["verified"].iloc[0]).lower() == "true"
        lic = rows["license"].iloc[0]
        for u in units.itertuples():
            display_rows.append(dict(
                unit_id=u.unit_id, iso3=iso3, level="ADM1", parent_id=iso3, name=u.name,
                unit_type_local=u.unit_type_local, unit_type_en=u.unit_type_en, method="national_conformed",
                source=f"{u.publisher}, {u.product}", source_vintage=u.vintage, license=lic, boundary_vintage=u.vintage,
                src_ref=u.src_ref, published=published, geometry=disp.at[u.unit_id, "geometry"],
            ))
        rep.update(n_units=len(units), parts=[{k: v for k, v in i.items() if k != "columns"} for i in infos],
                   coord_decimals=decimals or None, seconds=round(time.time() - t0, 1),
                   clean_mode=clean_mode, simplify=("yes" if simplify_on else "no"), coverage_cleaning=crep, simplification=ssum, rounding=rrep, neighbour_mask_adm1_countries=sorted(
                       set(published_adm1["iso3"]) & set(nb)) if published_adm1 is not None and len(published_adm1) else [],
                   units=unit_rep)
        if iso3 == "KOR" and any(i.get("merge") for i in infos):
            kd = law_creation_date(root, "KOR")
            rep["merge_creation_date"] = kd
            log(f"  KOR merged unit creation date: {kd['date']} ({kd['note']})")
        report[iso3] = rep
        for i, (_, r) in zip(infos, rows.iterrows()):
            sources.append(dict(publisher=r["publisher"], product=r["product"], url=r["url"], retrieved_at=i["retrieved_at"],
                                sha256=i["sha256"], license=r["license"], iso3=iso3, file=i["file"], attribution=r["attribution"]))
        log(f"  {iso3}: {len(units)} units; outside ADM0 before/after {rep['outside_adm0_km2_before']}/{rep['outside_adm0_km2_after']} km2; "
            f"land gap {rep['land_gap_initial_km2']} -> {rep['land_gap_residual_km2']} km2 ({rep['seconds']}s)")
    display = gpd.GeoDataFrame(display_rows, crs=c.CRS_WGS84)
    return display, analysis, report, sources, review_all, extras


# --------------------------------------------------------------------------
# Inspect mode (read-only look at the inputs; no ADM0 needed)
# --------------------------------------------------------------------------

def inspect_main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only look at the national inputs: prints codes and names per part.")
    ap.add_argument("--input-root", required=True, type=Path)
    ap.add_argument("--table", default=Path("boundaries/national_sources_v030.csv"), type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    table = load_table(a.table)
    lines = []

    def out(s=""):
        print(s, flush=True)
        lines.append(s)

    for iso3, rows in table.groupby("iso3", sort=False):
        if a.only and iso3 not in a.only:
            continue
        out(f"\n## {iso3}")
        for _, row in rows.iterrows():
            try:
                src, layer, fpath = locate(a.input_root, row)
                gdf = read_source(src, layer)
                units, info = prepare_part(row, gdf, fpath, a.input_root)
                out(f"part {row['part']}: {fpath.name} | rows {info['raw_n']} | columns {info['columns'][:40]}")
                out(f"  after filter {info.get('after_filter_n', '-')} | dissolved_from {info.get('dissolved_from', '-')} -> units {len(units)} (expected {row['expected_units']}) | vintage {info['vintage']}")
                if info.get("regroup_rows") is not None:
                    out(f"  regroup rows {info['regroup_rows']}: {info['regroup_names']}")
                    for r_ in info.get("regroup", []):
                        out(f"    rule {r_['rule']!r}: from {r_['from_groups']} to {r_['to']}; groups after: {r_['groups_after']}")
                    for r_ in info.get("regroup_skipped", []):
                        out(f"    rule NOT applied: {r_['rule']!r}: {r_['reason']}")
                if row["merge"]:
                    try:
                        units, minfo = apply_merge(iso3, units, row["merge"])
                        out(f"  merge OK: {minfo}")
                    except c.BuildError as e:
                        out(f"  MERGE STOP: {e}")
                pairs = list(zip(units["code"], units["name_src"]))
                out(f"  code -> name ({len(pairs)}): {pairs[:120]}")
                dec = max(max_decimals(g, 12) for g in gdf.geometry.values[:50] if g is not None and not g.is_empty) if len(gdf) else None
                out(f"  decimals in raw coordinates (first 50 objects): up to {dec}; CRS {gdf.crs.to_string() if gdf.crs else None}")
            except Exception as e:  # noqa: BLE001
                out(f"part {row['part']}: ERROR {type(e).__name__}: {e}")
    if a.out:
        a.out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwritten {a.out}")
    return 0


def texts_main(argv=None) -> int:
    """Read-only, takes seconds: the IDN rights search (ARCH7 r5 item 11) and the KOR creation date (item 1), without reading any geodata."""
    ap = argparse.ArgumentParser(description=texts_main.__doc__)
    ap.add_argument("--input-root", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    lines = []
    rs = rights_search(a.input_root, "IDN")
    lines += ["## IDN: search for a reservation of rights", rs["line"], ""]
    lines += [f"searched: {x['kind']:5s} {x['file']} ({x['chars']} chars)" for x in rs["searched"]]
    lines += [f"left out: {x['file']} -- {x['reason']}" for x in rs["excluded"]]
    lines += [f"unreadable: {x}" for x in rs["unreadable"]]
    lines += [f"HIT [{h['word']}] {h['file']}: ...{h['context']}..." for h in rs["hits"]]
    kd = law_creation_date(a.input_root, "KOR")
    lines += ["", "## KOR: creation date of 전남광주통합특별시 (부칙)", f"date: {kd['date']} (file {kd['file']})", f"note: {kd['note']}",
              f"saved law files: {kd['searched_files']}"]
    lines += [f"candidate date={x['date']} names_the_law={x['names_the_law']} {x['file']}: {x['context']}" for x in kd["candidates"]]
    text = "\n".join(lines)
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
        print(f"\nwritten {a.out}")
    return 0


def names_preview_main(argv=None) -> int:
    """Attributes only (no geometry, no ADM0, no cleaning): unit_id / name / ISO 3166-2 / how / flag of every national unit.
    Takes about a minute. Output: national_adm1_units_v030_preview.csv (same columns as national_adm1_units_v030.csv)."""
    ap = argparse.ArgumentParser(description=names_preview_main.__doc__)
    ap.add_argument("--input-root", required=True, type=Path)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    ap.add_argument("--out", default=Path("national_adm1_units_v030_preview.csv"), type=Path)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    global ATTRIBUTES_ONLY
    ATTRIBUTES_ONLY = True
    manifest = json.loads((a.sources_dir / "sources_manifest.json").read_text(encoding="utf-8"))
    table = load_table(a.boundaries_dir / "national_sources_v030.csv")
    names_tbl = load_names(a.boundaries_dir / "adm1_names_v030.csv")
    cldr = Cldr(manifest)
    allrev, problems = [], []
    for iso3, rows in table.groupby("iso3", sort=False):
        if a.only and iso3 not in a.only:
            continue
        try:
            units, _ = read_country(a.input_root, rows)
            _, review = resolve_names(iso3, units, rows, names_tbl, cldr)
            allrev.extend(review)
            print(f"{iso3}: {len(units)} units", flush=True)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{iso3}: {type(e).__name__}: {e}")
            print(f"{iso3}: ERROR {type(e).__name__}: {e}", flush=True)
    if allrev:
        pd.DataFrame(allrev).sort_values("unit_id").to_csv(a.out, index=False, encoding="utf-8")
        print(f"written {a.out}: {len(allrev)} units")
    if problems:
        print("PROBLEMS:\n" + "\n".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    if "--texts" in sys.argv:
        sys.argv.remove("--texts")
        raise SystemExit(texts_main())
    if "--names-preview" in sys.argv:
        sys.argv.remove("--names-preview")
        raise SystemExit(names_preview_main())
    if "--inspect" in sys.argv:
        sys.argv.remove("--inspect")
        raise SystemExit(inspect_main())
    print("bnd_national.py is a helper module; use --inspect or --texts with --input-root ... to look at the inputs.")
