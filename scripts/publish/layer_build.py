"""Builders of the abf-layers files and meta.json (helper module, not run directly).

Run command: none. This is a helper module, it is imported by build_release.py.

Two layer kinds are built here:
* ADM layers (level ADM2): one row per unit of the frame, `coverage_status`
  tells covered from not_covered (P2);
* line layers (level line): one row per segment, key `record_id`.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

import tilesio
from common import (
    GateError,
    Report,
    p9_hits,
    power_field_names,
    read_json,
    resolve_path,
    sha256_file,
)
from hifld_rights import RightsResult, check_hifld_rights

log = logging.getLogger("publish.layers")

BUILD_ONLY_KEYS = ("fill_na_covered", "min")  # in the yaml for the build, never published
OPTIONAL_REFS = {"source_workbook", "geometry_calc"}            # input_refs that may be absent on this machine

SERVICE_FIELDS = {
    "unit_id": {
        "name": "unit_id", "type": "string", "nullable": False,
        "description": "Unit code of the boundaries release: ISO3-level-national code, e.g. USA-2-51059.",
    },
    "fips": {
        "name": "fips", "type": "string", "nullable": False,
        "description": "County FIPS code, 5 digits, kept as a string (leading zeros matter).",
    },
    "name": {
        "name": "name", "type": "string", "nullable": False,
        "description": "Unit name as published in the boundaries release.",
    },
    "coverage_status": {
        "name": "coverage_status", "type": "string", "nullable": False,
        "description": "covered: the unit is inside the area the source was processed for; "
                       "not_covered: outside it, all values are empty (not zero).",
    },
    "coverage_note": {
        "name": "coverage_note", "type": "string", "nullable": True,
        "description": "Reason why the unit is not_covered, in English; empty for covered units.",
        "null_meaning": {
            "not_covered": "Not applicable: every not_covered unit has a reason in this field.",
            "covered": "The unit is covered, so there is no reason to give.",
        },
    },
}

OUTSIDE_NOTE_DEFAULTS = {"USA": "Alaska and Hawaii are not covered in this release."}  # units outside the processed area
GENERIC_OUTSIDE_NOTE = "This unit is not covered in this release."


# --------------------------------------------------------------------------- context
@dataclass
class Boundaries:
    """The boundaries release (output of CODE-BND) as the layers see it."""

    root: Path
    registry: pd.DataFrame
    name_overrides: pd.DataFrame | None = None  # boundaries/name_overrides.csv (names corrected after the boundaries release)
    _cache: dict[str, gpd.GeoDataFrame] = field(default_factory=dict)

    @staticmethod
    def norm_level(value: Any) -> str:
        text = str(value).strip().upper()
        if text.startswith("ADM"):
            return text
        if text.isdigit():
            return f"ADM{int(text)}"
        return text

    def read(self, rel: str) -> gpd.GeoDataFrame:
        if rel not in self._cache:
            path = self.root / rel
            if not path.exists():
                raise GateError("G4", f"boundaries file is missing: {path}")
            self._cache[rel] = tilesio.read_geo(path)
        return self._cache[rel]

    def verified(self, iso3: str, level: str) -> bool:
        reg = self.registry
        rows = reg[(reg["iso3"] == iso3) & (reg["level"].map(self.norm_level) == level)]
        return bool(len(rows) == 1 and str(rows.iloc[0]["verified"]).strip().lower() == "true")

    def analysis_path(self, iso3: str, level: str, optional: bool = False) -> Path | None:
        """Geometry for calculations; countries taken as-is from Natural Earth have none (display geometry is used)."""
        n = level.replace("ADM", "")
        found = sorted((self.root / "analysis").glob(f"{iso3}_adm{n}_*.parquet"))
        if not found and optional:
            return None
        if len(found) != 1:
            raise GateError("G4", f"expected exactly one analysis file for {iso3} {level}, found {found}")
        return found[0]


OVERRIDE_COLUMNS = ["unit_id", "name_source", "name", "source", "checked_at", "checked_by"]
NAME_OVERRIDE_PHRASE = "{n} unit names corrected from Natural Earth spelling to the INSEE official geographic code."


def _norm_name(value: Any) -> str:
    """Spelling-insensitive form for comparing names: NFC, one kind of apostrophe, single spaces."""
    import unicodedata
    text = unicodedata.normalize("NFC", str(value)).replace("\u2019", "'")
    return " ".join(text.split())


def apply_name_overrides(frame: pd.DataFrame, prefix: str, ctx: "BuildContext", layer_id: str) -> int:
    """Replace `name` in the frame by the corrected names of boundaries/name_overrides.csv.

    Only rows of this layer's level (unit_id starts with `prefix`) are used. Returns the number of
    names that really changed. The boundaries release itself is not touched.
    """
    ov = ctx.boundaries.name_overrides
    if ov is None:
        return 0
    rows = ov[ov["unit_id"].str.startswith(prefix)]
    if rows.empty:
        return 0
    if rows["unit_id"].duplicated().any():
        raise GateError("G4", f"{layer_id}: name_overrides.csv has repeated unit_id: "
                              f"{rows.loc[rows['unit_id'].duplicated(), 'unit_id'].tolist()}")
    empty = rows[rows["name"].str.strip() == ""]
    if len(empty):
        raise GateError("G4", f"{layer_id}: name_overrides.csv has an empty name for {empty['unit_id'].tolist()}")
    missing = sorted(set(rows["unit_id"]) - set(frame["unit_id"]))
    if missing:
        raise GateError("G4", f"{layer_id}: name_overrides.csv refers to units that are not in the frame: {missing}")
    current = frame.set_index("unit_id")["name"]
    changed: list[str] = []
    for _, r in rows.iterrows():
        old = current[r["unit_id"]]
        new = " ".join(r["name"].split())
        if r["name_source"].strip() and _norm_name(r["name_source"]) != _norm_name(old):
            ctx.report.warn(f"{layer_id}: name_overrides.csv expects the boundaries name '{r['name_source']}' for "
                            f"{r['unit_id']}, but the boundaries release has '{old}'; the corrected name is still used")
        if new != old:
            frame.loc[frame["unit_id"] == r["unit_id"], "name"] = new
            changed.append(f"{r['unit_id']}: {old} -> {new}")
    ctx.report.section(f"Corrected unit names ({layer_id})", [f"- {c}" for c in changed] or ["- none"])
    return len(changed)


@dataclass
class BuildContext:
    """Everything a layer builder needs."""

    release: dict[str, Any]
    channel: str
    out_dir: Path
    built_at: str            # 'YYYY-MM-DDTHH:MM:SSZ'
    published_at: str        # 'YYYY-MM-DD'
    doi: str | None
    boundaries: Boundaries
    report: Report
    overrides: dict[str, str] = field(default_factory=dict)
    tmp_dir: Path | None = None
    input_hashes: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.release["version"])

    @property
    def tag(self) -> str:
        return str(self.release["tag"])


@dataclass
class LayerOutput:
    layer_id: str
    meta: dict[str, Any]
    meta_path: Path
    files: dict[str, Path]
    tile_input: Path
    tile_build: dict[str, Any]
    bbox: list[float]
    archives: list[dict[str, Any]] = field(default_factory=list)
    extra_files: list[dict[str, Any]] = field(default_factory=list)
    title: str = ""
    domain: str = ""
    level: str = ""
    tile_fields: list[str] = field(default_factory=list)
    source_layer: str = ""
    geometry_type: str = "polygon"
    tile_cfg: dict[str, Any] = field(default_factory=dict)
    carries_power: bool = False   # G3b: the layer has fields from the ADR 6.2 power list


# --------------------------------------------------------------------------- helpers
def parse_date(value: Any) -> str:
    """'20260912', '2026-09-12' or an ISO datetime -> 'YYYY-MM-DD'."""
    text = str(value).strip()
    m = re.fullmatch(r"(\d{8})_r\d+", text)  # rebuild suffix of CODE-PILOT files: '20261009_r2'
    if m:
        text = m.group(1)
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if "T" in fmt or " " in fmt else text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"cannot read a date from {value!r}")


def hash_input(ctx: BuildContext, path: Path) -> dict[str, Any]:
    """SHA-256 of an input file, remembered for the G6 re-check at the end."""
    key = str(path)
    if key not in ctx.input_hashes:
        ctx.input_hashes[key] = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        log.info("input %s sha256=%s", path.name, ctx.input_hashes[key]["sha256"][:12])
    return ctx.input_hashes[key]


def cast_series(series: pd.Series, ftype: str) -> pd.Series:
    """Cast a column to the declared type of fields[]."""
    if ftype == "integer":
        return pd.to_numeric(series, errors="raise").astype("Int64")
    if ftype == "number":
        return pd.to_numeric(series, errors="raise").astype("float64")
    if ftype == "boolean":
        if series.dtype == object:
            mapped = series.map({"True": True, "False": False, "true": True, "false": False, True: True, False: False})
            return mapped.astype("boolean")
        return series.astype("boolean")
    return series.astype(object).where(series.notna(), None)


def service_field_names(cfg: dict[str, Any]) -> list[str]:
    """Service fields of an ADM layer. US layers keep `fips`; other countries have no such field."""
    names = cfg.get("frame", {}).get("service_fields")
    if names is None:
        return ["unit_id", "fips", "name", "coverage_status", "coverage_note"]
    if names[:1] != ["unit_id"] or "coverage_status" not in names or "name" not in names:
        raise GateError("G2", f"{cfg['layer_id']}: frame.service_fields must contain unit_id, name, coverage_status")
    unknown = [n for n in names if n not in SERVICE_FIELDS]
    if unknown:
        raise GateError("G2", f"{cfg['layer_id']}: unknown service fields {unknown}")
    names = [n for n in names if n != "coverage_note"]
    names.insert(names.index("coverage_status") + 1, "coverage_note")  # SPEC_META 2.2: right after coverage_status
    return names


def full_fields(cfg: dict[str, Any], adm: bool) -> list[dict[str, Any]]:
    """fields[] as published: service fields first (ADM layers), then the declared ones."""
    declared = [copy.deepcopy(f) for f in cfg["fields"]]
    for f in declared:
        for key in BUILD_ONLY_KEYS:
            f.pop(key, None)
    if not adm:
        return declared
    service_names = service_field_names(cfg)
    clash = [f["name"] for f in declared if f["name"] in service_names]
    if clash:
        raise GateError("G2", f"{cfg['layer_id']}: fields[] must not declare service fields {clash}; the build adds them")
    service = [copy.deepcopy(SERVICE_FIELDS[k]) for k in service_names]
    if cfg.get("_name_corrected"):
        for f in service:
            if f["name"] == "name":
                f["description"] = ("Unit name from the boundaries release; where it differs from the official "
                                    "geographic code, the official spelling is used (see verification.method).")
    return service + declared


def layer_license(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Layer licence = licence of the primary source; attribution of all sources."""
    primary = next((s for s in sources if s["role"] == "primary"), sources[0])
    lic = copy.deepcopy(primary["license"])
    texts: list[str] = []
    for src in [primary] + [s for s in sources if s is not primary]:
        text = src["license"]["attribution_text"].strip()
        if text and text not in texts:
            texts.append(text)
    lic["attribution_text"] = " ".join(texts)
    return lic


def gate_licences(layer_id: str, sources: list[dict[str, Any]]) -> None:
    """G5: no not_publishable; share_alike only for a single source."""
    for src in sources:
        family = src["license"]["family"]
        if family == "not_publishable":
            raise GateError("G5", f"{layer_id}: source {src['source_id']} licence is not publishable")
        if family == "share_alike" and len(sources) > 1:
            raise GateError("G5", f"{layer_id}: share-alike source {src['source_id']} cannot be combined (P3)")
    for src in sources:
        if src["publication_mode"] == "status_only":
            raise GateError("G5", f"{layer_id}: status_only source {src['source_id']} is not allowed in a value layer")


def resolve_input(cfg: dict[str, Any], ctx: BuildContext) -> Path:
    override = ctx.overrides.get(cfg["layer_id"])
    path = resolve_path(override or cfg["input"]["table"])
    if not path.exists():
        raise GateError("G6", f"{cfg['layer_id']}: input file not found: {path}")
    return path


def retrieved_at_of(source: dict[str, Any], cfg: dict[str, Any], table_path: Path) -> str:
    value = source.get("retrieved_at")
    if value not in (None, "legacy_meta"):
        return str(value)
    legacy = cfg["input"].get("legacy_meta")
    if not legacy:
        raise GateError("G1", f"{cfg['layer_id']}: retrieved_at is not set and there is no input.legacy_meta")
    legacy_path = resolve_path(legacy)
    if not legacy_path.exists():
        raise GateError("G1", f"{cfg['layer_id']}: legacy meta not found: {legacy_path}; set retrieved_at in the yaml")
    meta = read_json(legacy_path)
    if "snapshot_date" not in meta:
        raise GateError("G1", f"{legacy_path.name} has no snapshot_date; set retrieved_at in the yaml")
    return parse_date(meta["snapshot_date"])


def build_sources(
    cfg: dict[str, Any],
    ctx: BuildContext,
    table_path: Path,
    extra_inputs: dict[str, Path],
) -> list[dict[str, Any]]:
    """sources[] with computed inputs[] (file name, bytes, sha256)."""
    out = []
    refs = {"table": table_path, **extra_inputs}
    for raw in cfg["sources"]:
        src = copy.deepcopy(raw)
        names = src.pop("input_refs", [])
        src["inputs"] = []
        for name in names:
            if name not in refs and name in OPTIONAL_REFS:
                continue
            if name not in refs:
                raise GateError("G6", f"{cfg['layer_id']}: source {src['source_id']} refers to unknown input {name}")
            h = hash_input(ctx, refs[name])
            src["inputs"].append({"file": h["file"], "bytes": h["bytes"], "sha256": h["sha256"]})
        src["retrieved_at"] = retrieved_at_of(src, cfg, table_path) if src.get("retrieved_at") in (None, "legacy_meta") else str(src["retrieved_at"])
        src["current_through"] = None if src["current_through"] is None else str(src["current_through"])
        for key in ("checked_at",):
            if key in src.get("rights_basis", {}):
                src["rights_basis"][key] = str(src["rights_basis"][key])
        out.append(src)
    if cfg["layer_id"] in ctx.overrides:
        if ctx.channel == "final":
            raise GateError("G6", f"{cfg['layer_id']}: --override is not allowed in the final channel; "
                                  f"put the right file into the layer yaml")
        primary = next((x for x in out if x["role"] == "primary"), out[0])
        primary["edition"] = f"{primary['edition']} (DEV BUILD: input {table_path.name}, may be another edition)"
        ctx.report.warn(f"{cfg['layer_id']}: input replaced with {table_path.name}; the edition label is marked as DEV BUILD")
    return out


def fill_citation(text: str, ctx: BuildContext, title: str, layer_id: str) -> str:
    doi_url = f"https://doi.org/{ctx.doi}" if ctx.doi else "(development build, no DOI)"
    repl = {
        "{title}": title, "{version}": ctx.version, "{year}": ctx.published_at[:4],
        "{doi_url}": doi_url, "{tag}": ctx.tag, "{layer_id}": layer_id,
    }
    for key, value in repl.items():
        text = text.replace(key, value)
    return text


def coverage_iso3(cfg: dict[str, Any], frame_iso3: str | None) -> list[str]:
    """coverage.iso3: countries of the layer (SPEC_META 6 item 23). ADM layers default to the frame country."""
    value = cfg["coverage"].get("iso3")
    if value is None and frame_iso3:
        value = [frame_iso3]
    if not value or not isinstance(value, list) or not all(re.fullmatch(r"[A-Z]{3}", str(v)) for v in value):
        raise GateError("G1", f"{cfg['layer_id']}: coverage.iso3 must be a list of ISO3 codes, e.g. [USA]; got {value!r}")
    return [str(v) for v in value]


def home_bbox_of(cfg: dict[str, Any], ctx: "BuildContext") -> list[float] | None:
    """display.home_bbox: given as four numbers, or computed from boundaries units (`home_bbox_from`)."""
    disp = cfg.get("display", {})
    if disp.get("home_bbox") is not None:
        hb = [float(v) for v in disp["home_bbox"]]
        if len(hb) != 4 or hb[0] >= hb[2] or hb[1] >= hb[3]:
            raise GateError("G1", f"{cfg['layer_id']}: display.home_bbox must be [west, south, east, north], got {hb}")
        return hb
    rule = disp.get("home_bbox_from")
    if not rule:
        return None
    iso3, level = rule["iso3"], rule["level"]
    prefix = f"{iso3}-{level.replace('ADM', '')}-"
    all_units = ctx.boundaries.read(f"display/{level.lower()}.parquet")
    units = all_units[all_units["unit_id"].astype(str).str.startswith(prefix)]
    codes = units["unit_id"].astype(str).str[len(prefix):]
    chosen = units[codes.str.fullmatch(str(rule["code_regex"]))]
    if chosen.empty:
        raise GateError("G4", f"{cfg['layer_id']}: home_bbox_from selects no unit of {iso3} {level}")
    log.info("%s: home_bbox from %d of %d %s %s units", cfg["layer_id"], len(chosen), len(units), iso3, level)
    return tilesio.bbox_of(chosen)


def assemble_meta(
    cfg: dict[str, Any],
    ctx: BuildContext,
    sources: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    coverage: dict[str, Any],
    checks: list[dict[str, str]],
    display: dict[str, Any],
    extra_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """Meta in the key order of SPEC section 3.1."""
    primary = next((s for s in sources if s["role"] == "primary"), sources[0])
    fresh_cfg = cfg["freshness"]
    base_levels = sum(float(cfg["verification"]["levels"].get(k, 0)) for k in ("source_as_is", "script_rules", "human"))
    if abs(base_levels - 1.0) > 1e-6:
        raise GateError("G1", f"{cfg['layer_id']}: verification.levels source_as_is + script_rules + human must be 1, got {base_levels}")
    meta: dict[str, Any] = {
        "schema_version": "abf-meta-1.0",
        "kind": "layer",
        "layer_id": cfg["layer_id"],
        "title": cfg["title"],
    }
    if cfg.get("title_ru"):
        meta["title_ru"] = cfg["title_ru"]
    meta.update({
        "domain": cfg["domain"],
        "level": cfg["level"],
        "description": " ".join(str(cfg["description"]).split()),
        "fields": fields,
        "sources": sources,
        "license": layer_license(sources),
        "boundary_release": ctx.release.get("boundary_release") if cfg["level"] not in ("line", "point") else None,
        "freshness": {
            "source_current_through": primary["current_through"],
            "source_cadence": fresh_cfg["source_cadence"],
            "built_at": ctx.built_at,
            "next_check": str(fresh_cfg["next_check"]) if fresh_cfg.get("next_check") else None,
        },
        "coverage": coverage,
        "download_formats": ["parquet", "geojson.gz", "csv"],
        "release": {
            "dataset": ctx.release["dataset"],
            "version": ctx.version,
            "tag": ctx.tag,
            "doi": ctx.doi,
            "published_at": ctx.published_at,
        },
        "verification": {
            "levels": copy.deepcopy(cfg["verification"]["levels"]),
            "method": " ".join(str(cfg["verification"]["method"]).split()),
            "sample_share": copy.deepcopy(cfg["verification"].get("sample_share", {})),
            "automated_checks": checks,
        },
        "citation": {
            "text": fill_citation(" ".join(str(cfg["citation"]["text"]).split()), ctx, cfg["title"], cfg["layer_id"]),
            "record_pattern": fill_citation(cfg["citation"]["record_pattern"], ctx, cfg["title"], cfg["layer_id"]),
        },
    })
    home_bbox = home_bbox_of(cfg, ctx)
    if home_bbox is not None or display:
        display = {k: v for k, v in display.items() if k not in ("home_bbox", "home_bbox_from")}
        if home_bbox is not None:
            display["home_bbox"] = home_bbox
        meta["display"] = display
    if extra_files:
        meta["extra_files"] = extra_files
    return meta


def assemble_meta_boundaries(
    cfg: dict[str, Any],
    ctx: BuildContext,
    sources: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    coverage: dict[str, Any],
    checks: list[dict[str, str]],
    display: dict[str, Any],
) -> dict[str, Any]:
    """Meta of the boundaries dataset: `levels` instead of `level`, compilation licence (SPEC 2.3)."""
    lic = copy.deepcopy(cfg["license"])
    texts: list[str] = []
    for src in sources:
        t = src["license"]["attribution_text"].strip()
        if t and t not in texts:
            texts.append(t)
    lic["attribution_text"] = " ".join(texts)
    fresh = cfg["freshness"]
    primary = next((s for s in sources if s["role"] == "primary"), sources[0])
    meta: dict[str, Any] = {
        "schema_version": "abf-meta-1.0",
        "kind": "boundaries",
        "layer_id": cfg["layer_id"],
        "title": cfg["title"],
    }
    if cfg.get("title_ru"):
        meta["title_ru"] = cfg["title_ru"]
    meta.update({
        "domain": "boundaries",
        "levels": ["ADM0", "ADM1", "ADM2"],
        "description": " ".join(str(cfg["description"]).split()),
        "fields": fields,
        "sources": sources,
        "license": lic,
        "boundary_release": None,
        "freshness": {
            "source_current_through": primary["current_through"],
            "source_cadence": fresh["source_cadence"],
            "built_at": ctx.built_at,
            "next_check": str(fresh["next_check"]) if fresh.get("next_check") else None,
        },
        "coverage": coverage,
        "download_formats": ["parquet", "geojson.gz"],
        "release": {
            "dataset": ctx.release["dataset"], "version": ctx.version, "tag": ctx.tag,
            "doi": ctx.doi, "published_at": ctx.published_at,
        },
        "verification": {
            "levels": copy.deepcopy(cfg["verification"]["levels"]),
            "method": " ".join(str(cfg["verification"]["method"]).split()),
            "sample_share": copy.deepcopy(cfg["verification"].get("sample_share", {})),
            "automated_checks": checks,
        },
        "citation": {
            "text": fill_citation(" ".join(str(cfg["citation"]["text"]).split()), ctx, cfg["title"], cfg["layer_id"]),
            "record_pattern": fill_citation(cfg["citation"]["record_pattern"], ctx, cfg["title"], cfg["layer_id"]),
        },
        "display": display,
    })
    return meta


def gate_field_names(layer_id: str, names: list[str]) -> None:
    """G3: P9 field-name regular expression."""
    hits = p9_hits(names)
    if hits:
        raise GateError("G3", f"{layer_id}: field names match the P9 pattern: {hits}")


def gate_columns(layer_id: str, expected: list[str], files: dict[str, Path]) -> None:
    """G2: columns of every published file equal fields[] in composition and order."""
    for fmt, path in files.items():
        if fmt == "csv":
            cols = list(pd.read_csv(path, nrows=0).columns)
        elif fmt == "parquet":
            cols = [c for c in gpd.read_parquet(path).columns if c != "geometry"]
        else:
            continue
        if cols != expected:
            raise GateError("G2", f"{layer_id}: columns of {path.name} differ from fields[]: {cols} vs {expected}")


def read_geojson_columns(path_gz: Path) -> list[str]:
    """Property names of the first feature of a .geojson.gz."""
    import gzip
    with gzip.open(path_gz, "rt", encoding="utf-8") as fh:
        head = fh.read(200000)
    m = re.search(r'"properties"\s*:\s*\{(.*?)\}\s*,\s*"geometry"', head, re.S)
    if not m:
        raise GateError("G2", f"cannot find properties in {path_gz.name}")
    return list(json.loads("{" + m.group(1) + "}").keys())


# --------------------------------------------------------------------------- ADM layer
def build_adm_layer(cfg: dict[str, Any], ctx: BuildContext) -> LayerOutput:
    """One ADM2 layer: rows for all units of the frame, values for covered ones."""
    layer_id = cfg["layer_id"]
    report = ctx.report
    frame_cfg = cfg["frame"]
    iso3, level = frame_cfg["iso3"], frame_cfg["level"]
    log.info("== %s", layer_id)

    if not ctx.boundaries.verified(iso3, level):
        raise GateError("G12", f"{layer_id}: boundary registry row {iso3} {level} is not verified=true")

    table_path = resolve_input(cfg, ctx)
    hash_input(ctx, table_path)
    key = cfg["input"]["key"]
    df = pd.read_csv(table_path, dtype={key: str})
    df = df.rename(columns=cfg["input"].get("rename", {}))
    key = cfg["input"].get("rename", {}).get(key, key)
    for d in cfg["input"].get("derive", []):
        if d["op"] != "sum":
            raise GateError("G2", f"{layer_id}: unknown derive op {d['op']}")
        df[d["name"]] = df[d["columns"]].sum(axis=1)
    # The key column holds either the national code (US: 5-digit FIPS) or the full unit_id (France).
    code_regex = str(frame_cfg.get("code_regex", r"\d{5}"))
    unit_prefix = f"{iso3}-{level.replace('ADM', '')}-"
    if key not in df.columns:
        raise GateError("G2", f"{layer_id}: key column {key} is not in the input table; columns: {list(df.columns)[:30]}")
    if df[key].isna().any():
        raise GateError("G4", f"{layer_id}: key {key} is empty in {int(df[key].isna().sum())} rows")
    df[key] = df[key].astype(str).str.strip()
    full_ids = df[key].str.startswith(unit_prefix)
    if full_ids.any() and not full_ids.all():
        raise GateError("G4", f"{layer_id}: key {key} mixes full unit_id and national codes")
    codes = df[key].str[len(unit_prefix):] if full_ids.all() else df[key]
    if not codes.str.fullmatch(code_regex).all():
        bad_codes = df.loc[~codes.str.fullmatch(code_regex), key].tolist()[:5]
        raise GateError("G4", f"{layer_id}: key {key} must match {code_regex} for every row, bad: {bad_codes}")
    if df[key].duplicated().any():
        raise GateError("G4", f"{layer_id}: duplicated keys in the input table: "
                              f"{df.loc[df[key].duplicated(), key].tolist()[:5]}")
    df[key] = codes

    # frame: calc geometry (analysis) + names (display)
    calc_path = ctx.boundaries.analysis_path(iso3, level, optional=True)
    calc = ctx.boundaries.read(f"analysis/{calc_path.name}") if calc_path else None
    disp_all = ctx.boundaries.read(f"display/{level.lower()}.parquet")
    prefix = f"{iso3}-{level.replace('ADM', '')}-"
    disp = disp_all[disp_all["unit_id"].astype(str).str.startswith(prefix)].copy()
    if calc is None:
        report.section(f"Geometry ({layer_id})", [f"- no analysis file for {iso3} {level}: the display geometry of the boundaries release is used for the GeoParquet and GeoJSON files"])
        calc = disp.copy()
    calc = calc[calc["unit_id"].astype(str).str.startswith(prefix)].copy()
    if set(calc["unit_id"]) != set(disp["unit_id"]):
        raise GateError("G4", f"{layer_id}: analysis and display files hold different units "
                              f"({len(calc)} vs {len(disp)})")
    if disp["unit_id"].duplicated().any():
        raise GateError("G4", f"{layer_id}: duplicated unit_id in the boundaries display file")
    frame = disp[["unit_id", "name"]].sort_values("unit_id").reset_index(drop=True)
    n_renamed = apply_name_overrides(frame, prefix, ctx, layer_id)
    if n_renamed:
        # the corrected names are part of the published layer: say so in verification.method and in the field text
        cfg = copy.deepcopy(cfg)
        cfg["verification"]["method"] = (" ".join(str(cfg["verification"]["method"]).split()) + " "
                                         + NAME_OVERRIDE_PHRASE.format(n=n_renamed))
        cfg["_name_corrected"] = True
    frame["fips"] = frame["unit_id"].str[len(prefix):]
    if not frame["fips"].str.fullmatch(code_regex).all():
        raise GateError("G4", f"{layer_id}: unit_id of the frame does not end with a code matching {code_regex}")
    n_frame = len(frame)

    df["unit_id"] = prefix + df[key]
    unknown = sorted(set(df["unit_id"]) - set(frame["unit_id"]))
    if unknown:
        raise GateError("G4", f"{layer_id}: {len(unknown)} unit_id of the table are not in the boundaries: {unknown[:5]}")

    value_specs = [f for f in cfg["fields"] if f["name"] not in SERVICE_FIELDS]  # service names are added by the build
    missing = [f["name"] for f in value_specs if f["name"] not in df.columns]
    if missing:
        raise GateError("G2", f"{layer_id}: declared fields are not in the input table: {missing}")

    # Optional per-row coverage of the input (e.g. Connecticut planning regions in the queue file):
    # rows marked not_covered stay in the frame as not_covered with empty values; they are never
    # filled with 0 ("no data" is not "checked, nothing found").
    declared_nc: set[str] = set()
    row_notes: dict[str, str] = {}
    cov_col = cfg["input"].get("coverage_column")
    if cov_col:
        if cov_col not in df.columns:
            raise GateError("G2", f"{layer_id}: coverage column {cov_col} is not in the input table")
        bad_cov = sorted(set(df[cov_col].dropna().astype(str)) - {"covered", "not_covered"})
        if bad_cov or df[cov_col].isna().any():
            raise GateError("G4", f"{layer_id}: {cov_col} must be covered or not_covered in every row, got {bad_cov}")
        nc_rows = df[df[cov_col] == "not_covered"]
        for spec in value_specs:
            if nc_rows[spec["name"]].notna().any():
                raise GateError("G4", f"{layer_id}: {spec['name']} has values in rows marked not_covered")
        note_col = cfg["input"].get("coverage_note_column")
        notes = sorted({str(n) for n in nc_rows[note_col].dropna()}) if note_col and note_col in nc_rows else []
        if note_col and note_col in nc_rows:
            row_notes = {r["unit_id"]: " ".join(str(r[note_col]).split()) for _, r in nc_rows.iterrows()
                         if pd.notna(r[note_col]) and str(r[note_col]).strip()}
        declared_nc = set(nc_rows["unit_id"])
        report.section("Units marked not_covered by the input table", [
            f"- {layer_id}: {len(nc_rows)} units: {sorted(declared_nc)[:12]}"] + [f"  - note: {n}" for n in notes])
        df = df[df[cov_col] == "covered"].copy()

    # fill rule of [ARCH] 07.10: covered unit without value -> 0, meaning in description
    for spec in value_specs:
        if "fill_na_covered" in spec:
            n_na = int(df[spec["name"]].isna().sum())
            if n_na:
                df[spec["name"]] = df[spec["name"]].fillna(spec["fill_na_covered"])
                report.warn(f"{layer_id}: {n_na} covered units had no {spec['name']}, published as {spec['fill_na_covered']}")

    for spec in value_specs:
        if spec.get("min") is not None:
            bad = df[pd.to_numeric(df[spec["name"]], errors="coerce") < spec["min"]]
            if len(bad):
                report.warn(f"{layer_id}: {len(bad)} covered units have {spec['name']} below {spec['min']}: "
                            f"{bad['unit_id'].tolist()[:5]} values {bad[spec['name']].tolist()[:5]}")
                report.section("Values below the allowed minimum", [
                    f"- {layer_id}.{spec['name']}: {r['unit_id']} = {r[spec['name']]}" for _, r in bad.iterrows()])
    values = df[["unit_id"] + [f["name"] for f in value_specs]].copy()
    for spec in value_specs:
        values[spec["name"]] = cast_series(values[spec["name"]], spec["type"])
    table = frame.merge(values, on="unit_id", how="left", validate="one_to_one")
    covered_ids = set(df["unit_id"]) - declared_nc
    table["coverage_status"] = np.where(table["unit_id"].isin(covered_ids), "covered", "not_covered")
    # coverage_note: the reason, from the input table when it gives one, else the text for units outside
    # the processed area (SPEC_META 2.2); empty for covered units.
    outside_note = frame_cfg.get("outside_note") or OUTSIDE_NOTE_DEFAULTS.get(iso3)
    n_generic = 0
    notes_col: list[str | None] = []
    for uid, status in zip(table["unit_id"], table["coverage_status"]):
        if status == "covered":
            notes_col.append(None)
        elif uid in row_notes:
            notes_col.append(row_notes[uid])
        elif outside_note and uid not in declared_nc:
            notes_col.append(" ".join(str(outside_note).split()))
        else:
            notes_col.append(GENERIC_OUTSIDE_NOTE)
            n_generic += 1
    table["coverage_note"] = pd.Series(notes_col, index=table.index, dtype=object)
    if n_generic:
        report.warn(f"{layer_id}: {n_generic:,} not_covered units have no reason in the input table; "
                    f"the generic coverage_note is used")
    for spec in value_specs:
        table[spec["name"]] = cast_series(table[spec["name"]], spec["type"])
    order = service_field_names(cfg) + [f["name"] for f in value_specs]
    table = table[order]
    report_breaks(cfg, table, report)

    # G4: not_covered empty, covered empty only where null_meaning.covered allows
    nc = table["coverage_status"] == "not_covered"
    for spec in value_specs:
        col = table[spec["name"]]
        if col[nc].notna().any():
            raise GateError("G4", f"{layer_id}: {spec['name']} has values in not_covered rows")
        nm = spec.get("null_meaning")
        covered_allowed = isinstance(nm, dict) and nm.get("covered") is not None
        n_null = int(col[~nc].isna().sum())
        if n_null and not covered_allowed:
            raise GateError("G4", f"{layer_id}: {spec['name']} is empty in {n_null} covered units, "
                                  f"but null_meaning.covered is null")
    if table.loc[~nc, "coverage_note"].notna().any() or table.loc[nc, "coverage_note"].isna().any():
        raise GateError("G4", f"{layer_id}: coverage_note must be empty for covered units and given for every not_covered unit")
    fields = full_fields(cfg, adm=True)
    gate_field_names(layer_id, [f["name"] for f in fields])
    for f in fields:
        if f.get("nullable") and "null_meaning" not in f:
            raise GateError("G1", f"{layer_id}: field {f['name']} is nullable but has no null_meaning")

    # files
    out = ctx.out_dir
    files = {"csv": out / f"{layer_id}.csv", "parquet": out / f"{layer_id}.parquet",
             "geojson.gz": out / f"{layer_id}.geojson.gz"}
    tilesio.write_csv(table, files["csv"])
    geom = calc.set_index("unit_id").geometry
    gdf = gpd.GeoDataFrame(table.copy(), geometry=geom.reindex(table["unit_id"]).values, crs="EPSG:4326")
    tilesio.write_parquet(gdf, files["parquet"])
    tilesio.write_geojson_gz(gdf, files["geojson.gz"], layer_id, ctx.tmp_dir)
    covered_gdf = gdf[gdf["coverage_status"] == "covered"]
    bbox = tilesio.bbox_of(covered_gdf if len(covered_gdf) else gdf)

    # tile input: display geometry
    disp_geom = disp.set_index("unit_id").geometry
    tgdf = gpd.GeoDataFrame(table.copy(), geometry=disp_geom.reindex(table["unit_id"]).values, crs=disp.crs)
    display = copy.deepcopy(cfg.get("display", {}))
    tile_base = ["unit_id", "name", "coverage_status", "coverage_note"]
    tile_fields = tile_base + [t for t in (display.get("tile_fields") or [f["name"] for f in value_specs]) if t not in tile_base]
    gate_field_names(layer_id + " (tile fields)", tile_fields)
    display["tile_fields"] = tile_fields
    tile_in = out / "_tiles_input" / f"{layer_id}.geojsonseq.gz"
    tilesio.write_geojsonseq_gz(tgdf, tile_in, tile_fields, ctx.tmp_dir)

    # G2 read back
    gate_columns(layer_id, order, {"csv": files["csv"], "parquet": files["parquet"]})
    gj_cols = read_geojson_columns(files["geojson.gz"])
    if gj_cols != order:
        raise GateError("G2", f"{layer_id}: geojson.gz properties {gj_cols} differ from fields[]")

    # checks
    checks: list[dict[str, str]] = []
    extra_refs = {"geometry_display": ctx.boundaries.root / "display" / f"{level.lower()}.parquet"}
    if calc_path:
        extra_refs["geometry_calc"] = calc_path
    if cfg.get("source_archive"):
        extra_refs["archive"] = resolve_path(cfg["source_archive"]["path"])
    tvs_cfg = cfg.get("checks", {}).get("totals_vs_source")
    if tvs_cfg and resolve_path(tvs_cfg["source_file"]).exists():
        extra_refs["source_workbook"] = resolve_path(tvs_cfg["source_file"])
        hash_input(ctx, extra_refs["source_workbook"])
    sources = build_sources(cfg, ctx, table_path, extra_refs)
    gate_licences(layer_id, sources)
    checks.append({"id": "input_sha256", "description":
                   "SHA-256 of every input file was computed at the start and again at the end of the build; they match."})
    checks.append({"id": "frame_complete", "description":
                   f"The file has exactly one row for each of the {n_frame:,} {iso3} {level} units of the boundaries release; "
                   f"{int((~nc).sum()):,} are covered and {int(nc.sum()):,} are not_covered with empty values."})
    checks.append({"id": "unit_id_in_boundaries", "description":
                   "Every unit_id of the layer exists in the boundaries release and no unit_id is repeated."})
    checks.append({"id": "schema_fields", "description":
                   "Columns of the CSV, GeoParquet and GeoJSON files equal fields[] in composition and order."})
    read_back = pd.read_csv(files["csv"], dtype={"unit_id": str, "fips": str})
    for spec in value_specs:
        if spec["type"] in ("integer", "number"):
            src_sum = float(pd.to_numeric(df[spec["name"]]).sum())
            out_sum = float(read_back[spec["name"]].sum())
            if not np.isclose(src_sum, out_sum, rtol=1e-9, atol=1e-6):
                raise GateError("G4", f"{layer_id}: sum of {spec['name']} changed: {src_sum} -> {out_sum}")
    checks.append({"id": "sum_matches_build", "description":
                   "The sum of every numeric column read back from the published CSV equals the sum in the input table."})
    run_layer_checks(cfg, ctx, df, table, checks, report)

    hifld_gap = apply_rights_check(cfg, ctx, checks, sources, out, report)

    known_gaps = list(cfg["coverage"].get("known_gaps", []))
    if hifld_gap:
        known_gaps.append(hifld_gap)
    coverage = {
        "geography": cfg["coverage"]["geography"],
        "iso3": coverage_iso3(cfg, iso3),
        "frame": {"iso3": iso3, "level": level},
        "n_units_frame": n_frame,
        "n_units_covered": int((~nc).sum()),
        "n_records": int(len(table)),
        "known_gaps": known_gaps,
    }
    archives = collect_archives(cfg, ctx, out, sources)
    meta = assemble_meta(cfg, ctx, sources, fields, coverage, checks, display, [])
    meta_path = out / f"{layer_id}.meta.json"

    if hash_input(ctx, table_path)["sha256"] != sha256_file(table_path):
        raise GateError("G6", f"{layer_id}: input file changed during the build: {table_path.name}")

    tiles_cfg = cfg.get("tiles", {})
    build = {
        "output": f"{layer_id}.pmtiles",
        "inputs": [{"source_layer": layer_id, "input": f"_tiles_input/{layer_id}.geojsonseq.gz"}],
        "geometry_type": "polygon",
        "minzoom": int(tiles_cfg.get("minzoom", 0)),
        "maxzoom": int(tiles_cfg.get("maxzoom", 10)),
        "args": tiles_cfg.get("extra_args", ["--detect-shared-borders", "--no-tile-size-limit",
                                             "--no-feature-limit", "--simplify-only-low-zooms"]),
    }
    return LayerOutput(layer_id, meta, meta_path, files, tile_in, build, bbox, archives, [],
                       cfg["title"], cfg["domain"], cfg["level"], tile_fields, layer_id, "polygon", tiles_cfg)


def report_breaks(cfg: dict[str, Any], table: pd.DataFrame, report: Report) -> None:
    """Compare the approved class breaks with quantiles of the non-zero covered values.

    The approved breaks are not changed here. A quantile that moved by more than 20 %
    is listed, then [ARCH] decides (SPEC section 5).
    """
    disp = cfg.get("display", {})
    field_name, breaks = disp.get("value_field"), disp.get("breaks")
    if not field_name or not breaks or field_name not in table.columns:
        return
    covered = table.loc[table["coverage_status"] == "covered", field_name]
    nz = pd.to_numeric(covered, errors="coerce")
    nz = nz[nz > 0]
    if len(nz) < 10:
        return
    qs = [float(nz.quantile(q)) for q in (0.2, 0.4, 0.6, 0.8)]
    lines = [f"- {cfg['layer_id']}.{field_name}: {len(nz)} non-zero covered values; "
             f"approved breaks {breaks}; quantiles 20/40/60/80 %: {[round(q, 1) for q in qs]}"]
    moved = [(b, q) for b, q in zip(breaks, qs) if b and abs(q - b) / b > 0.20]
    if moved:
        lines.append(f"  - SHIFT over 20 % at {[(b, round(q, 1)) for b, q in moved]}: send to [ARCH]")
        report.warn(f"{cfg['layer_id']}: quantiles moved more than 20 % from the approved breaks: {moved}")
    report.section("Class breaks", lines)


def run_layer_checks(cfg, ctx, df, table, checks, report) -> None:  # noqa: ANN001
    """Layer specific checks named in the yaml `checks:` block."""
    layer_id = cfg["layer_id"]
    wanted = cfg.get("checks", {})
    if wanted.get("km_total_matches_has_any_line"):
        km_pos = table["km_total"].fillna(0) > 0
        has = table["has_any_line"].fillna(False).astype(bool)
        bad = table[(km_pos != has) & (table["coverage_status"] == "covered")]
        for _, row in bad.iterrows():
            report.warn(f"{layer_id}: km_total={row['km_total']} but has_any_line={row['has_any_line']} "
                        f"for {row['unit_id']} ({row['name']})")
        report.section("km_total vs has_any_line", [
            f"- covered units where `km_total > 0` differs from `has_any_line`: {len(bad)}"
        ] + [f"  - {r['unit_id']} {r['name']}: km_total={r['km_total']}, has_any_line={r['has_any_line']}"
             for _, r in bad.iterrows()])
        checks.append({"id": "km_total_matches_has_any_line", "description":
                       f"km_total > 0 exactly when has_any_line was tested for every covered unit; "
                       f"{len(bad)} divergences (lines shorter than rounding) are listed in the release report."})
    tvs = wanted.get("totals_vs_source")
    if tvs:
        run_totals_vs_source(layer_id, tvs, df, table, checks, report)


def _filter_mask(src: pd.DataFrame, rules: list[dict[str, Any]], layer_id: str, parsed: dict[str, pd.Series]) -> pd.Series:
    """Rows of the source table that satisfy every filter rule (row-wise AND).

    Rule keys: column, and one of equals / in / not_in / empty / not_empty / not_after (a date,
    with keep_empty: true an empty date also passes).
    """
    mask = pd.Series(True, index=src.index)
    for rule in rules:
        col = rule["column"]
        if col not in src.columns:
            raise GateError("G2", f"{layer_id}: totals_vs_source: filter column {col!r} is not in the source; "
                                  f"columns found: {list(src.columns)[:40]}")
        raw = src[col].astype(object)
        empty = raw.isna() | (raw.astype(str).str.strip() == "")
        text = raw.astype(str).str.strip().map(lambda v: unicodedata.normalize("NFC", v))
        if "equals" in rule:
            mask &= text == str(rule["equals"])
        elif "contains" in rule:
            mask &= text.str.lower().str.contains(str(rule["contains"]).lower(), regex=False)
        elif "in" in rule:
            mask &= text.isin([str(v) for v in rule["in"]])
        elif "not_in" in rule:
            mask &= ~text.isin([str(v) for v in rule["not_in"]])
        elif rule.get("empty"):
            mask &= empty
        elif rule.get("not_empty"):
            mask &= ~empty
        elif "not_after" in rule:
            key = f"date:{col}"
            if key not in parsed:
                dates = pd.to_datetime(text.where(~empty), errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
                bad = (~empty) & dates.isna()
                if bad.any():
                    raise GateError("G2", f"{layer_id}: totals_vs_source: {int(bad.sum())} values of {col} are not dates, "
                                          f"for example {text[bad].head(3).tolist()}")
                parsed[key] = dates
            ok = parsed[key] <= pd.Timestamp(str(rule["not_after"]))
            mask &= ok | (empty & bool(rule.get("keep_empty", False)))
        else:
            raise GateError("G2", f"{layer_id}: totals_vs_source: unknown filter rule {rule}")
    return mask


def run_csv_totals(layer_id, tvs, table, checks, report) -> None:  # noqa: ANN001
    """totals_vs_source for a source that is a CSV table (France): recompute every listed layer column.

    For each entry of `columns:` the source rows pass the common `filters:` and the entry's own
    filters, are split into the units of the layer by the code column, and compared with the layer
    column unit by unit and in total. Rows of the `outside:` categories (ordered, first match
    wins; no code, codes outside the frame) are not units of the layer: they are listed, and the
    layer total plus them must equal the source total.
    """
    src_path = resolve_path(tvs["source_file"])
    if not src_path.exists():
        report.warn(f"{layer_id}: totals_vs_source not run, source file not found: {src_path}")
        return
    sep = tvs.get("separator", ",")
    if sep == "auto":  # the delimiter that is most frequent in the header line
        with src_path.open(encoding=tvs.get("encoding", "utf-8-sig"), errors="replace") as fh:
            head = fh.readline()
        sep = max([";", ",", "\t"], key=head.count)
    src = pd.read_csv(src_path, sep=sep, dtype=str, keep_default_na=False,
                      encoding=tvs.get("encoding", "utf-8-sig"), low_memory=False)
    code_col = tvs["code_column"]
    if code_col not in src.columns:
        raise GateError("G2", f"{layer_id}: totals_vs_source: code column {code_col!r} is not in the source; "
                              f"columns found: {list(src.columns)[:40]}")
    decimal = tvs.get("decimal", ".")
    codes = src[code_col].astype(str).str.strip().str.upper().str.replace(r"\.0+$", "", regex=True)
    codes = codes.where(~codes.isin(["NAN", "NONE", "NULL"]), "")
    if tvs.get("code_zfill"):
        digits = codes.str.fullmatch(r"\d+")
        codes = codes.where(~digits, codes.str.zfill(int(tvs["code_zfill"])))
    unit_prefix = tvs["unit_prefix"]
    layer_units = table["unit_id"].astype(str)
    covered = table["coverage_status"] == "covered"
    parsed: dict[str, pd.Series] = {}
    base = _filter_mask(src, tvs.get("filters", []), layer_id, parsed)
    # outside categories, ordered and disjoint
    left = pd.Series(True, index=src.index)
    outside_rows: list[dict[str, Any]] = []
    outside_masks: list[pd.Series] = []
    for rule in tvs.get("outside", []):
        if rule.get("empty_code"):
            hit = codes == ""
        elif "codes" in rule:
            hit = codes.isin([str(c) for c in rule["codes"]])
        elif rule.get("not_in_frame"):
            hit = ~(unit_prefix + codes).isin(set(layer_units))
        else:
            raise GateError("G2", f"{layer_id}: totals_vs_source: unknown outside rule {rule}")
        hit = hit & left
        left &= ~hit
        outside_masks.append(hit)
        outside_rows.append({"name": rule["name"]})
    in_frame = left & (unit_prefix + codes).isin(set(layer_units))
    stray = base & left & ~in_frame
    if stray.any():
        raise GateError("G4", f"{layer_id}: totals_vs_source: {int(stray.sum())} counted source rows have a code that is neither a "
                              f"unit of the layer nor in the listed outside categories: {sorted(set(codes[stray]))[:8]}")
    tol = float(tvs.get("tolerance", 0.0005))
    lines: list[str] = []
    done: list[str] = []
    for entry in tvs["columns"]:
        lcol = entry["layer_column"]
        vcol = entry["value_column"]
        if vcol not in src.columns:
            raise GateError("G2", f"{layer_id}: totals_vs_source: value column {vcol!r} is not in the source; "
                                  f"columns found: {list(src.columns)[:40]}")
        raw_vals = src[vcol].astype(str).str.replace("\u00a0", "").str.replace(" ", "")
        if decimal != ".":
            raw_vals = raw_vals.str.replace(decimal, ".", regex=False)
        vals = pd.to_numeric(raw_vals, errors="coerce") / float(entry.get("divisor", 1))
        mask = base & _filter_mask(src, entry.get("filters", []), layer_id, parsed)
        n_nonnum = int((mask & vals.isna()).sum())
        vals = vals.fillna(0.0)
        by_unit = vals[mask & in_frame].groupby((unit_prefix + codes)[mask & in_frame]).sum()
        layer_vals = pd.to_numeric(table.set_index("unit_id")[lcol], errors="coerce")
        cov_ids = table.loc[covered, "unit_id"]
        expected = by_unit.reindex(cov_ids).fillna(0.0)
        diff = (layer_vals.reindex(cov_ids) - expected).abs()
        bad = diff[diff > tol]
        if len(bad):
            raise GateError("G4", f"{layer_id}.{lcol}: {len(bad)} units differ from the source by more than {tol}; first: "
                                  + "; ".join(f"{u}: layer {layer_vals[u]}, source {expected[u]}" for u in bad.index[:6]))
        src_total = float(vals[mask & base].sum())
        out_parts = [(r["name"], int((mask & m).sum()), float(vals[mask & m].sum())) for r, m in zip(outside_rows, outside_masks)]
        layer_sum = float(layer_vals[covered.values].sum())
        gap = src_total - layer_sum - sum(v for _, _, v in out_parts)
        lines.append(f"- {layer_id}.{lcol}: source {src_total:.4f}, layer {layer_sum:.4f}, outside the units "
                     + ", ".join(f"{n}: {c} rows / {v:.4f}" for n, c, v in out_parts)
                     + f"; difference after the categories {gap:.6f}; rows without a number: {n_nonnum}")
        if abs(gap) > tol * max(1, len(cov_ids)):
            raise GateError("G4", f"{layer_id}.{lcol}: source total {src_total:.4f} != layer {layer_sum:.4f} + outside categories "
                                  f"{[(n, v) for n, _, v in out_parts]}")
        done.append(lcol)
    report.section(f"totals_vs_source ({layer_id})", lines)
    outside_text = "; ".join(f"{n} {c} rows" for n, c, _ in out_parts) if tvs.get("outside") else "none"
    checks.append({"id": "totals_vs_source", "description":
                   f"The source table was filtered by the stated rules and summed again by unit: {len(done):,} layer columns "
                   f"({', '.join(done)}) equal the recomputed sums in every covered unit; the source total equals the layer total "
                   f"plus the rows outside the units ({outside_text})."})


def run_totals_vs_source(layer_id, tvs, df, table, checks, report) -> None:  # noqa: ANN001
    """Recompute the MW total from the source workbook and compare (SPEC section 7)."""
    if tvs.get("kind") == "csv":
        run_csv_totals(layer_id, tvs, table, checks, report)
        return
    src_path = resolve_path(tvs["source_file"])
    if not src_path.exists():
        report.warn(f"{layer_id}: totals_vs_source not run, source file not found: {src_path}")
        return
    value_col = tvs["layer_column"]
    layer_sum = float(pd.to_numeric(table[value_col]).sum())
    src = pd.read_excel(src_path, sheet_name=tvs["sheet"], header=tvs.get("header_row", 1))
    needed = [tvs["status_column"], tvs["state_column"]]
    lost = [c for c in needed if c not in src.columns]
    if lost:
        raise GateError("G2", f"{layer_id}: totals_vs_source: columns {lost} are not in sheet {tvs['sheet']!r} "
                              f"(header_row={tvs.get('header_row', 1)}); columns found: {list(src.columns)[:40]}")
    src = src[src[tvs["status_column"]].astype(str).str.strip() == tvs["status_value"]]
    mw_cols = tvs["mw_column"] if isinstance(tvs["mw_column"], list) else [tvs["mw_column"]]
    code_col = tvs.get("code_column")
    absent = [c for c in mw_cols + ([code_col] if code_col else []) if c not in src.columns]
    if absent:
        raise GateError("G2", f"{layer_id}: totals_vs_source: columns {absent} are not in the source sheet; "
                              f"columns found: {list(src.columns)[:40]}")
    nums = pd.concat([pd.to_numeric(src[c], errors="coerce") for c in mw_cols], axis=1)
    if tvs.get("mw_mode", "sum") == "max":
        # rule of [CODE-PILOT] for the queue: the capacity of a request is the max of its numeric MW columns
        src = src.assign(_mw=nums.max(axis=1))
        if tvs.get("exclude_nonpositive", False) and not tvs.get("derived_exceptions"):
            neg = src[~(src["_mw"] > 0) & src["_mw"].notna()]
            report.section("totals_vs_source rows excluded as non-positive", [
                f"- {layer_id}: {len(neg)} requests, {float(neg['_mw'].sum()):.1f} MW"])
            src = src[src["_mw"] > 0]
    else:
        src = src.assign(_mw=nums.fillna(0).sum(axis=1))
    if tvs.get("derived_exceptions"):
        run_reconciliation(layer_id, tvs, src, layer_sum, table, checks, report)
        return
    in_states = src[tvs["state_column"]].isin(tvs["states"])
    # diagnostics for the message: how the rows without a county code are spread over states
    diag = ""
    if code_col:
        nocode = src[code_col].isna() | (src[code_col].astype(str).str.strip().isin(["", "nan", "NA"]))
        diag = (f"; rows without {code_col}: {int(nocode.sum())} ({float(src.loc[nocode, '_mw'].sum()):.1f} MW), "
                f"of them in the listed states {int((nocode & in_states).sum())} "
                f"({float(src.loc[nocode & in_states, '_mw'].sum()):.1f} MW)")
    src = src[in_states]
    src_total = float(src["_mw"].sum())
    listed = tvs.get("exceptions") or []
    residual = src_total - layer_sum
    exceptions = round(sum(float(e["mw"]) for e in listed), 6) if listed else None
    report.section("totals_vs_source", [
        f"- {layer_id}: source total {src_total:.3f} MW ({len(src)} rows), layer total {layer_sum:.3f} MW, "
        f"difference {residual:.3f} MW, recorded exceptions {exceptions}"
    ])
    if exceptions is None:
        report.warn(f"{layer_id}: totals_vs_source difference is {residual:.3f} MW but no recorded exceptions "
                    f"(offshore, no county) are set in the yaml; the check is NOT written to automated_checks")
        return
    tol = float(tvs.get("tolerance_mw", 0.5))
    if abs(residual - float(exceptions)) > tol:
        raise GateError("G4", f"{layer_id}: totals_vs_source: difference {residual:.3f} MW, "
                              f"recorded exceptions {exceptions} MW, tolerance {tol} MW{diag}")
    checks.append({"id": "totals_vs_source", "description":
                   f"The {tvs['status_value']} capacity total of the source workbook for the listed states "
                   f"was recomputed ({src_total:.1f} MW) and equals the layer total ({layer_sum:.1f} MW) plus "
                   f"the recorded exceptions ({float(exceptions):.1f} MW: {'; '.join(str(e['name']) + ' ' + str(e['mw']) for e in listed)})."})


def run_reconciliation(layer_id, tvs, src, layer_sum, table, checks, report) -> None:  # noqa: ANN001
    """Split all active requests of the source into disjoint categories, in the order of the yaml rules.

    What is left after the rules must equal the layer (count and MW). Order and wording: [ARCH] 09.10.
    """
    state_col, code_col = tvs["state_column"], tvs.get("code_column")
    nocode = (src[code_col].isna() | src[code_col].astype(str).str.strip().isin(["", "nan", "NA"])) if code_col else None
    left = pd.Series(True, index=src.index)
    rows: list[dict[str, Any]] = []
    for rule in tvs["derived_exceptions"]:
        if rule.get("nonpositive"):
            hit = src["_mw"] <= 0
        elif rule.get("no_number"):
            hit = src["_mw"].isna()
        elif rule.get("outside_states"):
            hit = ~src[state_col].isin(tvs["states"])
        elif rule.get("empty_code"):
            hit = nocode
        else:
            hit = src[state_col].isin(rule["states"])
        hit = hit & left
        left &= ~hit
        rows.append({"name": rule["name"], "n": int(hit.sum()), "mw": round(float(src.loc[hit, "_mw"].sum()), 3)})
    kept = src[left]
    kept_mw, kept_n = float(kept["_mw"].sum()), len(kept)
    count_col = tvs.get("count_column")
    layer_n = int(pd.to_numeric(table[count_col]).sum()) if count_col else None
    lines = [f"- {layer_id}: {len(src)} active requests in the source = {kept_n} in the layer + "
             + " + ".join(f"{r['n']} ({r['name']})" for r in rows)]
    lines += [f"  - {r['name']}: {r['n']} requests, {r['mw']} MW" for r in rows]
    lines.append(f"  - in the layer: {kept_n} requests, {kept_mw:.3f} MW (layer total {layer_sum:.3f} MW"
                 + (f", {layer_n} projects)" if layer_n is not None else ")"))
    report.section("totals_vs_source categories", lines)
    tol = float(tvs.get("tolerance_mw", 0.5))
    if abs(kept_mw - layer_sum) > tol or (layer_n is not None and layer_n != kept_n):
        raise GateError("G4", f"{layer_id}: totals_vs_source: after the listed categories the source has {kept_n} requests / "
                              f"{kept_mw:.3f} MW, the layer has {layer_n} / {layer_sum:.3f} MW; " + "; ".join(
                                  f"{r['name']}: {r['n']} / {r['mw']} MW" for r in rows))
    checks.append({"id": "totals_vs_source", "description":
                   f"All {len(src):,} {tvs['status_value']} requests of the source workbook were split into disjoint categories "
                   f"and recomputed: {kept_n} requests ({kept_mw:.1f} MW) equal the layer; excluded: "
                   + "; ".join(f"{r['name']} {r['n']} requests ({r['mw']:.1f} MW)" for r in rows) + "."})


def apply_rights_check(cfg, ctx, checks, sources, out, report) -> str | None:  # noqa: ANN001
    """HIFLD section 10 check, when the layer config asks for it. Returns a known_gaps line."""
    rc = cfg.get("rights_check")
    if not rc:
        return None
    archive = resolve_path(rc["archive"])
    if not archive.exists():
        raise GateError("G6", f"{cfg['layer_id']}: HIFLD archive not found: {archive}")
    ext = resolve_path(rc["external_html"]) if rc.get("external_html") else None
    result: RightsResult = check_hifld_rights(archive, ext, rc["expected"],
                                              publish_name=(cfg.get("source_archive") or {}).get("publish_as"))
    for w in result.warnings:
        report.warn(f"{cfg['layer_id']}: {w}")
    if result.check_id:
        checks.append({"id": result.check_id, "description": result.check_description})
    report.section(f"HIFLD rights fields ({cfg['layer_id']})", [f"- mode: {result.mode}"] + [
        f"- {k}: {str(v)[:300]}" for k, v in result.fields.items()])
    if result.published_xml is not None:
        dst = out / "sources" / result.published_xml_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(result.published_xml)
        for s in sources:
            if s["source_id"] == rc.get("source_id"):
                s["rights_basis"]["evidence_url"] = f"sources/{result.published_xml_name}"
    return result.known_gap


def collect_archives(cfg, ctx, out, sources) -> list[dict[str, Any]]:  # noqa: ANN001
    """Copy the source archive next to the release (sources/<name>) when configured."""
    arch = cfg.get("source_archive")
    result: list[dict[str, Any]] = []
    if arch:
        src = resolve_path(arch["path"])
        if not src.exists():
            raise GateError("G6", f"{cfg['layer_id']}: source archive not found: {src}")
        publish_name = arch.get("publish_as") or src.name
        dst = out / "sources" / publish_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copyfile(src, dst)
        description = arch["description"]
        if publish_name != src.name:
            description += f" Original file name: {src.name}."
        result.append({"file": dst, "description": description})
    xml_dir = out / "sources"
    if xml_dir.exists():
        for xml in sorted(xml_dir.glob("*.metadata.xml")):
            result.append({"file": xml, "description": "Dataset metadata read from the source archive (XML)."})
    return result


# --------------------------------------------------------------------------- line layer
def voltage_band(kv: pd.Series, cls: pd.Series, class_map: dict[str, str]) -> tuple[pd.Series, dict[str, int]]:
    """Band from numeric voltage_kv (SPEC section 6); the class only when there is no number.

    < 100, 100-199, 200-299, 300-399, 400-599, >= 600; empty, zero or a missing-value
    code (-999999) -> unknown; direct current -> dc by the class field.
    """
    allowed = {"lt100", "100_199", "200_299", "300_399", "400_599", "ge600", "dc", "unknown"}
    bad_map = {k: v for k, v in class_map.items() if v not in allowed}
    if bad_map:
        raise GateError("G1", f"voltage_band class_map has values outside the band list (quote labels like \"100_199\" in the yaml): {bad_map}")
    kv = pd.to_numeric(kv, errors="coerce")
    has_num = kv.notna() & (kv > 0) & (kv != -999999)
    band = pd.Series("unknown", index=kv.index, dtype=object)
    cuts = [(100, "lt100"), (200, "100_199"), (300, "200_299"), (400, "300_399"), (600, "400_599")]
    band[has_num] = "ge600"
    for upper, label in reversed(cuts):
        band[has_num & (kv < upper)] = label
    no_num = ~has_num
    cls_norm = cls.astype(object).where(cls.notna(), "").astype(str).str.strip()
    mapped = cls_norm.map(class_map).fillna("unknown")
    band[no_num] = mapped[no_num]
    dc = cls_norm.str.upper() == "DC"
    band[dc] = "dc"
    stats = {
        "from_number": int(has_num.sum()),
        "from_class": int((no_num & (mapped != "unknown")).sum()),
        "unknown": int((band == "unknown").sum()),
        "dc": int(dc.sum()),
    }
    return band, stats


def build_line_layer(cfg: dict[str, Any], ctx: BuildContext) -> LayerOutput:
    """The segments layer: one row per line segment, key record_id."""
    layer_id = cfg["layer_id"]
    report = ctx.report
    log.info("== %s", layer_id)
    table_path = resolve_input(cfg, ctx)
    hash_input(ctx, table_path)
    gdf = pyogrio.read_dataframe(table_path)
    gdf = gdf.rename(columns=cfg["input"].get("rename", {}))
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        log.info("%s: reprojecting to EPSG:4326", table_path.name)
        gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)

    gdf["record_id"] = gdf["record_id"].astype(object).where(gdf["record_id"].notna(), "")
    gdf["record_id"] = gdf["record_id"].astype(str).str.strip()
    if (gdf["record_id"] == "").any():
        raise GateError("G4", f"{layer_id}: empty record_id in {int((gdf['record_id'] == '').sum())} rows")
    if gdf["record_id"].duplicated().any():
        raise GateError("G4", f"{layer_id}: record_id is not unique")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise GateError("G4", f"{layer_id}: empty geometry in some segments")

    vb_cfg = cfg["voltage_band"]
    band, vstats = voltage_band(gdf["voltage_kv"], gdf["voltage_class"], vb_cfg["class_map"])
    gdf["voltage_band"] = band
    # SPEC_META section 6 item 2 (ARCH 10.10): the missing-value code -999999 and values <= 0 are published as empty.
    kv_num = pd.to_numeric(gdf["voltage_kv"], errors="coerce")
    n_code = int((kv_num == -999999).sum())
    n_nonpos = int(((kv_num <= 0) & (kv_num != -999999)).sum())
    gdf["voltage_kv"] = kv_num.where(kv_num > 0)
    report.section(f"voltage_band ({layer_id})", [
        f"- from the numeric voltage: {vstats['from_number']}",
        f"- from the class (no number): {vstats['from_class']}",
        f"- unknown: {vstats['unknown']}",
        f"- dc (by class field): {vstats['dc']}",
        f"- voltage_kv equal to the missing-value code -999999 (published as empty): {n_code}",
        f"- voltage_kv of zero or less, other than the code (published as empty): {n_nonpos}",
        f"- voltage_kv empty in the published file: {int(gdf['voltage_kv'].isna().sum())}",
        f"- counts by band: {band.value_counts().to_dict()}",
    ])

    specs = cfg["fields"]
    names = [f["name"] for f in specs]
    missing = [n for n in names if n not in gdf.columns]
    if missing:
        raise GateError("G2", f"{layer_id}: declared fields not in the input: {missing}")
    table = gdf[names].copy()
    for spec in specs:
        table[spec["name"]] = cast_series(table[spec["name"]], spec["type"])
    order = names
    sort = table["record_id"].argsort(kind="stable")
    table = table.iloc[sort].reset_index(drop=True)
    geom = gdf.geometry.iloc[sort].reset_index(drop=True)
    for spec in specs:
        n_null = int(table[spec["name"]].isna().sum())
        if n_null and not spec.get("nullable"):
            raise GateError("G4", f"{layer_id}: {spec['name']} has {n_null} empty values but is not nullable")

    fields = full_fields(cfg, adm=False)
    gate_field_names(layer_id, [f["name"] for f in fields])

    out = ctx.out_dir
    files = {"csv": out / f"{layer_id}.csv", "parquet": out / f"{layer_id}.parquet",
             "geojson.gz": out / f"{layer_id}.geojson.gz"}
    tilesio.write_csv(table, files["csv"])
    out_gdf = gpd.GeoDataFrame(table.copy(), geometry=geom.values, crs="EPSG:4326")
    tilesio.write_parquet(out_gdf, files["parquet"])
    tilesio.write_geojson_gz(out_gdf, files["geojson.gz"], layer_id, ctx.tmp_dir)
    bbox = tilesio.bbox_of(out_gdf)

    display = copy.deepcopy(cfg.get("display", {}))
    tile_fields = display.get("tile_fields") or names
    gate_field_names(layer_id + " (tile fields)", tile_fields)
    display["tile_fields"] = tile_fields
    tiles_cfg = cfg.get("tiles", {})
    mz_map = tiles_cfg.get("minzoom_by_band", {})
    minzoom = table["voltage_band"].map(mz_map) if mz_map else None
    tile_in = out / "_tiles_input" / f"{layer_id}.geojsonseq.gz"
    tilesio.write_geojsonseq_gz(out_gdf, tile_in, tile_fields, ctx.tmp_dir, minzoom)

    gate_columns(layer_id, order, {"csv": files["csv"], "parquet": files["parquet"]})
    gj_cols = read_geojson_columns(files["geojson.gz"])
    if gj_cols != order:
        raise GateError("G2", f"{layer_id}: geojson.gz properties {gj_cols} differ from fields[]")
    # G10: every record carries its reference (the source's own id)
    ref_field = cfg.get("ref_field", "record_id")
    if table[ref_field].isna().any() or (table[ref_field].astype(str) == "").any():
        raise GateError("G10", f"{layer_id}: records without {ref_field}")

    checks = [
        {"id": "input_sha256", "description":
         "SHA-256 of every input file was computed at the start and again at the end of the build; they match."},
        {"id": "schema_fields", "description":
         "Columns of the CSV, GeoParquet and GeoJSON files equal fields[] in composition and order."},
        {"id": "record_id_unique", "description":
         f"record_id (the HIFLD ID) is present and unique in all {len(table):,} segments; none has an empty geometry."},
    ]
    sources = build_sources(cfg, ctx, table_path, {"archive": resolve_path(cfg["source_archive"]["path"])
                                                   if cfg.get("source_archive") else table_path})
    gate_licences(layer_id, sources)
    hifld_gap = apply_rights_check(cfg, ctx, checks, sources, out, report)
    known_gaps = list(cfg["coverage"].get("known_gaps", []))
    if hifld_gap:
        known_gaps.append(hifld_gap)
    gap = f"{vstats['unknown']:,} of {len(table):,} segments have no usable voltage; their voltage_band is unknown."
    if vstats["from_class"]:
        gap += f" {vstats['from_class']:,} more have no numeric voltage and take the band of their voltage_class."
    known_gaps.append(gap)
    coverage = {
        "geography": cfg["coverage"]["geography"],
        "iso3": coverage_iso3(cfg, None),
        "frame": None, "n_units_frame": None, "n_units_covered": None,
        "n_records": int(len(table)),
        "known_gaps": known_gaps,
    }
    archives = collect_archives(cfg, ctx, out, sources)
    meta = assemble_meta(cfg, ctx, sources, fields, coverage, checks, display, [])
    if hash_input(ctx, table_path)["sha256"] != sha256_file(table_path):
        raise GateError("G6", f"{layer_id}: input file changed during the build: {table_path.name}")
    build = {
        "output": f"{layer_id}.pmtiles",
        "inputs": [{"source_layer": layer_id, "input": f"_tiles_input/{layer_id}.geojsonseq.gz"}],
        "geometry_type": "line",
        "minzoom": int(tiles_cfg.get("minzoom", 0)),
        "maxzoom": int(tiles_cfg.get("maxzoom", 11)),
        "args": tiles_cfg.get("extra_args", ["--drop-densest-as-needed", "--extend-zooms-if-still-dropping"]),
    }
    return LayerOutput(layer_id, meta, out / f"{layer_id}.meta.json", files, tile_in, build, bbox,
                       archives, [], cfg["title"], cfg["domain"], cfg["level"], tile_fields, layer_id, "line", tiles_cfg)


# --------------------------------------------------------------------------- point layer
def apply_g3b(cfg: dict[str, Any], names: list[str], table: pd.DataFrame, checks: list[dict[str, str]]) -> bool:
    """G3b for a layer of the domain dc: power-like fields only from the ADR 6.2 list, one basis per record.

    Returns True if the layer carries power fields. A layer without them passes.
    """
    layer_id = cfg["layer_id"]
    bad, allowed = power_field_names(names)
    if bad:
        raise GateError("G3b", f"{layer_id}: fields look like power or capacity but are not on the ADR 6.2 list: {bad}")
    if "power_basis" in table.columns:
        basis = table["power_basis"].dropna().astype(str)
        multi = basis[~basis.str.fullmatch(r"[a-z][a-z0-9_]*")]
        if len(multi):
            raise GateError("G3b", f"{layer_id}: power_basis must be one code per record, got {sorted(set(multi))[:5]}")
    if allowed:
        checks.append({"id": "power_fields_adr", "description":
                       f"Power fields of the layer ({', '.join(allowed)}) are on the ADR 6.2 list; each record has one power basis."})
    else:
        checks.append({"id": "no_power_fields", "description":
                       "No field of the layer, of its files or of its tiles carries a power, capacity, generator or load value."})
    return bool(allowed)


def build_point_layer(cfg: dict[str, Any], ctx: BuildContext) -> LayerOutput:
    """A layer of records with a point (level point): one row per record, key record_id.

    Records whose coord_precision is none keep their row and have an empty geometry (P2).
    """
    layer_id = cfg["layer_id"]
    report = ctx.report
    log.info("== %s", layer_id)
    table_path = resolve_input(cfg, ctx)
    hash_input(ctx, table_path)
    specs = cfg["fields"]
    names = [f["name"] for f in specs]
    str_cols = {f["name"]: str for f in specs if f["type"] == "string"}
    raw = pd.read_csv(table_path, dtype=str_cols, keep_default_na=False, na_values=[""])
    raw = raw.rename(columns=cfg["input"].get("rename", {}))
    missing = [n for n in names if n not in raw.columns]
    if missing:
        raise GateError("G2", f"{layer_id}: declared fields are not in the input: {missing}; columns: {list(raw.columns)[:30]}")
    table = raw[names].copy()
    for spec in specs:
        table[spec["name"]] = cast_series(table[spec["name"]], spec["type"])
    table = table.sort_values("record_id", kind="stable").reset_index(drop=True)

    rid = table["record_id"].astype(object)
    if rid.isna().any() or (rid.astype(str).str.strip() == "").any():
        raise GateError("G4", f"{layer_id}: empty record_id in some rows")
    if rid.duplicated().any():
        raise GateError("G4", f"{layer_id}: record_id is not unique: {rid[rid.duplicated()].tolist()[:5]}")
    for spec in specs:
        n_null = int(table[spec["name"]].isna().sum())
        if n_null and not spec.get("nullable"):
            raise GateError("G4", f"{layer_id}: {spec['name']} has {n_null} empty values but is not nullable")
    for f in specs:
        if f.get("nullable") and "null_meaning" not in f:
            raise GateError("G1", f"{layer_id}: field {f['name']} is nullable but has no null_meaning")

    # geometry: lon/lat; precision none <-> no coordinates
    gcfg = cfg.get("geometry", {})
    lon_c, lat_c = gcfg.get("lon", "lon"), gcfg.get("lat", "lat")
    prec_c = gcfg.get("precision", "coord_precision")
    for c in (lon_c, lat_c, prec_c):
        if c not in table.columns:
            raise GateError("G2", f"{layer_id}: geometry column {c} is not among the fields")
    lon, lat = pd.to_numeric(table[lon_c], errors="coerce"), pd.to_numeric(table[lat_c], errors="coerce")
    none_prec = table[prec_c].astype(str) == "none"
    has_xy = lon.notna() & lat.notna()
    if (none_prec & has_xy).any() or (~none_prec & ~has_xy).any():
        raise GateError("G4", f"{layer_id}: coordinates and {prec_c} disagree: precision none must have empty "
                              f"{lon_c}/{lat_c}, every other precision must have both")
    bad_xy = has_xy & ~lon.between(-180, 180) | has_xy & ~lat.between(-90, 90)
    if bad_xy.any():
        raise GateError("G4", f"{layer_id}: coordinates out of range in {int(bad_xy.sum())} rows")
    bounds = gcfg.get("bounds")  # [west, south, east, north]: all points of the layer must lie inside
    if bounds:
        w, s_, e, n = bounds
        outside = has_xy & ~(lon.between(w, e) & lat.between(s_, n))
        if outside.any():
            raise GateError("G4", f"{layer_id}: {int(outside.sum())} points lie outside {bounds}: "
                                  f"{table.loc[outside, 'record_id'].tolist()[:5]}")
    allowed_prec = gcfg.get("precisions")
    if allowed_prec:
        wrong = sorted(set(table[prec_c].astype(str)) - set(allowed_prec))
        if wrong:
            raise GateError("G4", f"{layer_id}: {prec_c} has values outside {allowed_prec}: {wrong}")

    # units of the boundaries release
    uc = cfg.get("unit_check")
    checks: list[dict[str, str]] = [
        {"id": "input_sha256", "description":
         "SHA-256 of every input file was computed at the start and again at the end of the build; they match."},
        {"id": "schema_fields", "description":
         "Columns of the CSV, GeoParquet and GeoJSON files equal fields[] in composition and order."},
        {"id": "record_id_unique", "description":
         f"record_id is present and unique in all {len(table):,} records."},
    ]
    if uc:
        if not ctx.boundaries.verified(uc["iso3"], uc["level"]):
            raise GateError("G12", f"{layer_id}: boundary registry row {uc['iso3']} {uc['level']} is not verified=true")
        disp = ctx.boundaries.read(f"display/{uc['level'].lower()}.parquet")
        known = set(disp["unit_id"].astype(str))
        col = uc.get("column", "unit_id")
        unknown = sorted(set(table[col].dropna().astype(str)) - known)
        if unknown:
            raise GateError("G4", f"{layer_id}: {len(unknown)} {col} values are not in the boundaries release: {unknown[:5]}")
        checks.append({"id": "unit_id_in_boundaries", "description":
                       f"Every {col} of the layer exists in the boundaries release ({uc['iso3']} {uc['level']})."})
    if gcfg.get("bounds"):
        checks.append({"id": "points_inside_country", "description":
                       "Every point lies inside the bounding box of the country of the layer."})
    checks.append({"id": "coords_match_precision", "description":
                   f"Records with {prec_c} none have no coordinates; every other record has a longitude and a latitude in range."})

    # G10: every record carries its reference
    ref_field = cfg.get("ref_field", "ref")
    refs = table[ref_field].astype(object)
    if refs.isna().any() or (refs.astype(str).str.strip() == "").any():
        raise GateError("G10", f"{layer_id}: records without {ref_field}")
    checks.append({"id": "ref_present", "description": f"Every record has a non-empty {ref_field} (reference to the source record)."})

    fields = full_fields(cfg, adm=False)
    gate_field_names(layer_id, [f["name"] for f in fields])
    carries_power = False
    if cfg["domain"] == "dc":
        carries_power = apply_g3b(cfg, [f["name"] for f in fields], table, checks)

    out = ctx.out_dir
    files = {"csv": out / f"{layer_id}.csv", "parquet": out / f"{layer_id}.parquet",
             "geojson.gz": out / f"{layer_id}.geojson.gz"}
    tilesio.write_csv(table, files["csv"])
    from shapely.geometry import Point
    geoms = [Point(x, y) if ok else None for x, y, ok in zip(lon, lat, has_xy)]
    out_gdf = gpd.GeoDataFrame(table.copy(), geometry=gpd.GeoSeries(geoms, crs="EPSG:4326"), crs="EPSG:4326")
    tilesio.write_parquet(out_gdf, files["parquet"])
    tilesio.write_geojson_gz(out_gdf, files["geojson.gz"], layer_id, ctx.tmp_dir)
    with_geom = out_gdf[has_xy.values]
    if not len(with_geom):
        raise GateError("G4", f"{layer_id}: no record has a point")
    bbox = tilesio.bbox_of(with_geom)

    display = copy.deepcopy(cfg.get("display", {}))
    tile_fields = display.get("tile_fields") or names
    gate_field_names(layer_id + " (tile fields)", tile_fields)
    if cfg["domain"] == "dc":
        bad_t, _ = power_field_names(tile_fields)
        if bad_t:
            raise GateError("G3b", f"{layer_id}: tile fields look like power but are not on the ADR 6.2 list: {bad_t}")
    display["tile_fields"] = tile_fields
    tiles_cfg = cfg.get("tiles", {})
    tile_in = out / "_tiles_input" / f"{layer_id}.geojsonseq.gz"
    tilesio.write_geojsonseq_gz(with_geom, tile_in, tile_fields, ctx.tmp_dir)

    gate_columns(layer_id, names, {"csv": files["csv"], "parquet": files["parquet"]})
    gj_cols = read_geojson_columns(files["geojson.gz"])
    if gj_cols != names:
        raise GateError("G2", f"{layer_id}: geojson.gz properties {gj_cols} differ from fields[]")

    sources = build_sources(cfg, ctx, table_path, {})
    gate_licences(layer_id, sources)
    n_no_point = int((~has_xy).sum())
    report.section(f"Point layer ({layer_id})", [
        f"- {len(table)} records, {int(has_xy.sum())} with a point, {n_no_point} without",
        f"- {prec_c}: {table[prec_c].value_counts().to_dict()}",
        f"- power fields present: {carries_power}",
    ])
    coverage = {
        "geography": cfg["coverage"]["geography"],
        "iso3": coverage_iso3(cfg, None),
        "frame": None, "n_units_frame": None, "n_units_covered": None,
        "n_records": int(len(table)),
        "known_gaps": list(cfg["coverage"].get("known_gaps", [])),
    }
    meta = assemble_meta(cfg, ctx, sources, fields, coverage, checks, display, [])
    if hash_input(ctx, table_path)["sha256"] != sha256_file(table_path):
        raise GateError("G6", f"{layer_id}: input file changed during the build: {table_path.name}")
    build = {
        "output": f"{layer_id}.pmtiles",
        "inputs": [{"source_layer": layer_id, "input": f"_tiles_input/{layer_id}.geojsonseq.gz"}],
        "geometry_type": "point",
        "minzoom": int(tiles_cfg.get("minzoom", 0)),
        "maxzoom": int(tiles_cfg.get("maxzoom", 12)),
        # a few dozen points: keep all of them at every zoom (no dot dropping)
        "args": tiles_cfg.get("extra_args", ["--no-tile-size-limit", "--no-feature-limit", "-r1"]),
    }
    lo = LayerOutput(layer_id, meta, out / f"{layer_id}.meta.json", files, tile_in, build, bbox,
                     [], [], cfg["title"], cfg["domain"], cfg["level"], tile_fields, layer_id, "point", tiles_cfg)
    lo.carries_power = carries_power
    return lo
