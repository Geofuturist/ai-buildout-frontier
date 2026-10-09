"""Builder of the abf-boundaries dataset (helper module, not run directly).

Run command: none. This is a helper module, it is imported by build_release.py.

Input is the finished output of CODE-BND (read only). Nothing is rebuilt: files are
read, checked, copied under the names of SPEC section 4.2, and `units.csv` is made.
"""
from __future__ import annotations

import copy
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

import tilesio
from common import CYRILLIC_REGEX, GateError, resolve_path
from layer_build import (
    Boundaries,
    BuildContext,
    LayerOutput,
    assemble_meta_boundaries,
    gate_field_names,
    gate_licences,
    hash_input,
)

log = logging.getLogger("publish.boundaries")

UNIT_COLUMNS = ["unit_id", "iso3", "level", "name", "parent_id", "adm0_status",
                "source", "license", "boundary_vintage"]
REQUIRED_FOR_UNITS = ["unit_id", "iso3", "level", "name", "parent_id"]
LEVEL_FILES = {"adm0": "ADM0", "adm1": "ADM1", "adm2": "ADM2"}


@dataclass
class BoundariesOutput:
    layers: list[LayerOutput]
    meta: dict[str, Any]
    meta_path: Path
    extra_files: list[dict[str, Any]]
    tile_build: dict[str, Any]
    report_lines: list[str] = field(default_factory=list)


def _registry_row(reg: pd.DataFrame, iso3: str, level: str) -> pd.Series:
    rows = reg[(reg["iso3"] == iso3) & (reg["level"].map(Boundaries.norm_level) == level)]
    if len(rows) != 1:
        raise GateError("G12", f"boundary registry has {len(rows)} rows for {iso3} {level}, expected 1")
    return rows.iloc[0]


def make_units(adm0: gpd.GeoDataFrame, adm1: gpd.GeoDataFrame, adm2: gpd.GeoDataFrame,
               registry: pd.DataFrame, notes: list[str]) -> pd.DataFrame:
    """units.csv: one row per unit, without geometry."""
    parts = []
    status = adm0.set_index("iso3")["adm0_status"].to_dict() if "adm0_status" in adm0.columns else {}
    for name, gdf in (("adm0", adm0), ("adm1", adm1), ("adm2", adm2)):
        missing = [c for c in REQUIRED_FOR_UNITS if c not in gdf.columns]
        if missing:
            raise GateError("units.csv", f"display/{name}.parquet has no column(s) {missing}: "
                                         f"stop and ask [ARCH]/[CODE-BND]")
        df = pd.DataFrame(gdf.drop(columns="geometry")).copy()
        df["level"] = df["level"].map(Boundaries.norm_level)
        df["adm0_status"] = df["iso3"].map(status) if name != "adm0" else df.get("adm0_status")
        if name == "adm0":
            for col, own in (("source", "source"), ("license", "license"), ("boundary_vintage", "boundary_vintage")):
                if own not in df.columns:
                    raise GateError("units.csv", f"display/adm0.parquet has no column {own} (NE record)")
        else:
            src, lic, vint = [], [], []
            for _, row in df.iterrows():
                reg = _registry_row(registry, row["iso3"], row["level"])
                src.append(reg["source_name"])
                lic.append(reg["license"])
                vint.append(reg["source_vintage"])
            df["source"], df["license"], df["boundary_vintage"] = src, lic, vint
            if "boundary_vintage" in gdf.columns:
                diff = int((gdf["boundary_vintage"].astype(str).values != df["boundary_vintage"].astype(str).values).sum())
                if diff:
                    notes.append(f"units.csv {name}: boundary_vintage of the registry differs from the display file in {diff} rows; the registry value is published (rule of [ARCH])")
        parts.append(df[UNIT_COLUMNS])
    units = pd.concat(parts, ignore_index=True)
    if units["unit_id"].duplicated().any():
        raise GateError("G4", "unit_id is not unique across adm0/adm1/adm2")
    for col in ("adm0_status",):
        n_empty = int(units[col].isna().sum())
        if n_empty:
            notes.append(f"units.csv: adm0_status is empty in {n_empty} rows (no ADM0 record for the country)")
    return units.sort_values(["level", "unit_id"], kind="stable").reset_index(drop=True)


def build_boundaries(cfg: dict[str, Any], ctx: BuildContext, rel_cfg: dict[str, Any]) -> BoundariesOutput:
    """Build all files of abf-boundaries and the shared meta."""
    layer_id = cfg["layer_id"]
    root = ctx.boundaries.root
    file_map: dict[str, str] = rel_cfg["file_map"]
    out = ctx.out_dir
    report_lines: list[str] = []
    notes: list[str] = []
    registry = ctx.boundaries.registry

    # inputs hashed up front (G6)
    for rel in file_map:
        p = root / f"{rel}.parquet"
        if not p.exists():
            raise GateError("G4", f"boundaries output file is missing: {p}")
        hash_input(ctx, p)

    levels: dict[str, gpd.GeoDataFrame] = {}
    for lvl in ("adm0", "adm1", "adm2"):
        gdf = ctx.boundaries.read(f"display/{lvl}.parquet")
        if lvl != "adm0":
            for (iso3, level), _ in gdf.groupby(["iso3", gdf["level"].map(Boundaries.norm_level)]):
                if not ctx.boundaries.verified(iso3, level):
                    raise GateError("G12", f"{iso3} {level} is in display/{lvl}.parquet but verified is not true in the registry")
        if gdf["unit_id"].duplicated().any():
            raise GateError("G4", f"duplicated unit_id in display/{lvl}.parquet")
        levels[lvl] = gdf

    published_cols = cfg["published_columns"]
    layer_outputs: list[LayerOutput] = []
    tile_inputs: list[dict[str, Any]] = []
    tile_fields_cfg = cfg["display"]["tile_fields_by_layer"]
    for rel, name in file_map.items():
        if not rel.startswith("display/"):
            continue
        gdf = ctx.boundaries.read(f"{rel}.parquet")
        cols = [c for c in published_cols[name] if c in gdf.columns]
        absent = [c for c in published_cols[name] if c not in gdf.columns]
        if absent:
            raise GateError("G2", f"boundaries {name}: declared columns missing in the input: {absent}")
        dropped = [c for c in gdf.columns if c not in cols and c != "geometry"]
        if dropped:
            report_lines.append(f"- {name}: input columns not published (not declared in fields[]): {dropped}")
        sub = gdf[cols + ["geometry"]].sort_values("unit_id", kind="stable").reset_index(drop=True)
        base = f"boundaries_{name}"       # layer_id in the manifest
        files = {"parquet": out / f"{name}.parquet", "geojson.gz": out / f"{name}.geojson.gz"}
        tilesio.write_parquet(sub, files["parquet"])
        tilesio.write_geojson_gz(sub, files["geojson.gz"], base, ctx.tmp_dir)
        tf = tile_fields_cfg[name]
        tile_in = out / "_tiles_input" / f"{base}.geojsonseq.gz"
        tilesio.write_geojsonseq_gz(sub, tile_in, tf, ctx.tmp_dir)
        bbox = tilesio.bbox_of(sub)
        lcfg = cfg["tiles"]["layers"][name]
        tile_inputs.append({"source_layer": name, "input": f"_tiles_input/{base}.geojsonseq.gz",
                            "minzoom": lcfg["minzoom"], "maxzoom": lcfg["maxzoom"]})
        gate_field_names(f"{base} (tile fields)", tf)
        layer_outputs.append(LayerOutput(
            layer_id=base,
            meta={}, meta_path=out / f"{layer_id}.meta.json",
            files=files, tile_input=tile_in, tile_build={}, bbox=bbox,
            title=f"Boundaries · {name}", domain="boundaries",
            level="ADM0" if name in ("adm0", "disputed_unassigned") else name.upper(),
        ))
        layer_outputs[-1].tile_fields = tf
        layer_outputs[-1].source_layer = name
        layer_outputs[-1].tile_cfg = lcfg
        report_lines.append(f"- {name}: {len(sub)} rows, bbox {bbox}")

    # counts of the release (SPEC section 12 item 6: 242 / 89 / 3602)
    counts = {k: len(v) for k, v in levels.items()}
    report_lines.append(f"- unit counts: {counts}")

    # analysis files, copied under the names of SPEC section 4.2
    extra: list[dict[str, Any]] = []
    for rel, name in file_map.items():
        if rel.startswith("display/"):
            continue
        src = root / f"{rel}.parquet" if not Path(rel).suffix else root / rel
        if rel.startswith("analysis/"):
            if not src.exists():
                raise GateError("G4", f"analysis file is missing: {src}")
            gdf = tilesio.read_geo(src)
            dst = out / f"{name}.parquet"
            tilesio.write_parquet(gdf, dst)
            extra.append({"file": dst, "description": f"Geometry used for calculations ({name.replace('analysis_', '').upper().replace('_', ' ')}), EPSG:4326; not for display."})

    # units.csv
    units = make_units(levels["adm0"], levels["adm1"], levels["adm2"], registry, notes)
    units_path = out / "units.csv"
    tilesio.write_csv(units, units_path)
    extra.append({"file": units_path, "description": "List of all units without geometry: unit_id, iso3, level, name, parent_id, adm0_status, source, license, boundary_vintage."})
    report_lines += [f"- {n}" for n in notes]

    # reference files of the boundaries release
    for key, desc in (("registry", "Boundary registry: method, source, licence and verification status of every country and level."),
                      ("adm0_overrides", "Overrides applied to ADM0 status of countries."),
                      ("holes_whitelist", "Reviewed list of holes in the boundary geometry that are accepted as they are."),
                      ("validation_report", "Validation report of the boundaries build."),
                      ("unit_hashes", "Hash of the geometry of every unit.")):
        p = _reference_path(rel_cfg, ctx, key)
        if p is None:
            continue
        dst = out / p.name
        check_reference_text(p)
        shutil.copyfile(p, dst)
        hash_input(ctx, p)
        extra.append({"file": dst, "description": desc})

    # fields[] = union of the published columns, with the descriptions of the yaml
    fields = copy.deepcopy(cfg["fields"])
    declared = {f["name"] for f in fields}
    used = {c for cols in published_cols.values() for c in cols}
    if used - declared:
        raise GateError("G2", f"published columns without fields[] entry: {sorted(used - declared)}")
    fields = [f for f in fields if f["name"] in used]
    gate_field_names(layer_id, [f["name"] for f in fields])
    for f in fields:
        if f.get("nullable") and "null_meaning" not in f:
            raise GateError("G1", f"{layer_id}: field {f['name']} is nullable but has no null_meaning")

    # sources: upstream inputs from the BND meta.json
    sources = _boundaries_sources(cfg, ctx)
    gate_licences(layer_id, sources)
    checks = [
        {"id": "input_sha256", "description":
         "SHA-256 of every input file was computed at the start and again at the end of the build; they match."},
        {"id": "frame_complete", "description":
         f"Unit counts of the release were counted from the files: ADM0 {counts['adm0']}, ADM1 {counts['adm1']}, ADM2 {counts['adm2']}; "
         f"unit_id is unique across all levels."},
        {"id": "registry_verified", "description":
         "Every country and level with ADM1 or ADM2 units in the release has verified = true in the boundary registry."},
        {"id": "schema_fields", "description":
         "Columns of every published Parquet file are declared in fields[]."},
    ]
    for lo in layer_outputs:
        cols = list(gpd.read_parquet(lo.files["parquet"]).columns)
        cols = [c for c in cols if c != "geometry"]
        undeclared = [c for c in cols if c not in declared]
        if undeclared:
            raise GateError("G2", f"{lo.layer_id}: columns not declared in fields[]: {undeclared}")

    coverage = {
        "geography": cfg["coverage"]["geography"],
        "frame": None, "n_units_frame": None, "n_units_covered": None,
        "n_records": int(sum(counts.values())),
        "known_gaps": list(cfg["coverage"].get("known_gaps", [])),
    }
    display = {"tile_fields": sorted({t for v in tile_fields_cfg.values() for t in v})}
    meta = assemble_meta_boundaries(cfg, ctx, sources, fields, coverage, checks, display)
    tile_build = {
        "output": "boundaries.pmtiles",
        "inputs": tile_inputs,
        "geometry_type": "polygon",
        "minzoom": int(cfg["tiles"]["minzoom"]),
        "maxzoom": int(cfg["tiles"]["maxzoom"]),
        "args": cfg["tiles"].get("extra_args", ["--detect-shared-borders", "--no-tile-size-limit", "--no-feature-limit"]),
    }
    for lo in layer_outputs:
        lo.tile_build = tile_build
    return BoundariesOutput(layer_outputs, meta, out / f"{layer_id}.meta.json", extra, tile_build, report_lines)


def check_reference_text(path: Path) -> None:
    """G7: a reference file of the boundaries release is public text; Cyrillic is not allowed in it."""
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        m = CYRILLIC_REGEX.search(line)
        if m:
            raise GateError("G7", f"Cyrillic in the public reference file {path.name}, line {n}, "
                                  f"near: {line[max(0, m.start() - 30):m.start() + 30]!r}")


def _reference_path(rel_cfg: dict[str, Any], ctx: BuildContext, key: str) -> Path | None:
    """Reference files: registry etc. live in the repository, the rest in the BND output."""
    inputs = rel_cfg.get("reference_files", {})
    value = inputs.get(key)
    if not value:
        return None
    path = resolve_path(value, ctx.boundaries.root) if not str(value).startswith(("boundaries", "D:", "d:")) else resolve_path(value)
    if not path.exists():
        raise GateError("G6", f"reference file is missing: {path}")
    return path


def _boundaries_sources(cfg: dict[str, Any], ctx: BuildContext) -> list[dict[str, Any]]:
    """sources[] of abf-boundaries; upstream hashes come from the CODE-BND meta.json."""
    bnd_meta_path = ctx.boundaries.root / "meta.json"
    bnd_sources: list[dict[str, Any]] = []
    if bnd_meta_path.exists():
        import json
        bnd_sources = json.loads(bnd_meta_path.read_text(encoding="utf-8")).get("sources", [])
    else:
        ctx.report.warn("boundaries meta.json of CODE-BND not found: upstream hashes are not recorded")
    result = []
    for raw in cfg["sources"]:
        src = copy.deepcopy(raw)
        match = src.pop("bnd_match", [])
        inputs = []
        for item in bnd_sources:
            product = str(item.get("product", ""))
            if item.get("publisher") == src["publisher"] and any(m in product for m in match):
                inputs.append({"file": product, "bytes": None, "sha256": item["sha256"]})
        if not inputs:
            raise GateError("G6", f"{src['source_id']}: no upstream record with a SHA-256 in the boundaries meta.json")
        src["inputs"] = sorted(inputs, key=lambda x: x["file"])
        src["retrieved_at"] = str(src["retrieved_at"])
        src["current_through"] = str(src["current_through"])
        for key in ("checked_at",):
            if key in src.get("rights_basis", {}):
                src["rights_basis"][key] = str(src["rights_basis"][key])
        result.append(src)
    return result
