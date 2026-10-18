"""Builder of the abf-boundaries dataset (helper module, not run directly).

Run command: none. This is a helper module, it is imported by build_release.py.

Input is the finished output of CODE-BND (read only). Nothing is rebuilt: files are
read, checked, copied under the names of SPEC section 4.2, and `units.csv` is made.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

import tilesio
from registry_rows import read_records
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
# layers that are not a level of their own: shown in the manifest as ADM0 (like the unassigned areas)
LEVEL_OF_LAYER = {"adm0": "ADM0", "adm1": "ADM1", "adm2": "ADM2",
                  "disputed_unassigned": "ADM0", "contested_areas": "ADM0"}
VERDICT_REGEX = re.compile(r"verdict\W{0,3}(confirmed|disputed|refer_arch)\b", re.I)
# description of every reference file of the release that may be named in `reference_files` of the release yaml
REFERENCE_DESCRIPTIONS = {
    "registry": "Boundary registry: method, source, license and verification status of every country and level.",
    "adm0_overrides": "Overrides applied to ADM0 status of countries.",
    "adm0_patches": "Patches to the geometry of countries (in this release, Adjara added to Georgia).",
    "name_overrides": "Corrections of unit names, each with its source and the name it replaces.",
    "contested_areas": "Contested areas: state in control, claiming state, date, sources and checks. Input of the contested_areas layer.",
    "adm1_plan": "Plan of the first-level units added in version 0.2.0, one row per unit.",
    "adm1_leftovers": "Areas that belong to a country but to none of its first-level units, with their areas in km2.",
    "code_overrides": "Written corrections to the ISO 3166-2 code list applied when the first-level units were planned.",
    "holes_whitelist": "Reviewed list of holes in the boundary geometry that are accepted as they are.",
    "validation_report": "Validation report of the boundaries build.",
    "unit_hashes": "Hash of the geometry of every unit.",
    "license_unicode": "Unicode License v3 notice for the CLDR data used: codes and English names of first-level units.",
}


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

    if rel_cfg.get("registry_frozen_rows"):
        check_registry_frozen_rows(rel_cfg, report_lines)

    # inputs hashed up front (G6)
    for rel in file_map:
        p = root / f"{rel}.parquet"
        if not p.exists():
            raise GateError("G4", f"boundaries output file is missing: {p}")
        hash_input(ctx, p)

    if "contested_areas" in file_map.values() and rel_cfg.get("contested_areas_columns_from_reference"):
        join_contested_columns(ctx, rel_cfg, report_lines)

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
        sort_key = "area_id" if name == "contested_areas" else "unit_id"   # the contested areas have no unit_id
        sub = gdf[cols + ["geometry"]].sort_values(sort_key, kind="stable").reset_index(drop=True)
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
            level=LEVEL_OF_LAYER[name],
        ))
        layer_outputs[-1].tile_fields = tf
        layer_outputs[-1].source_layer = name
        layer_outputs[-1].tile_cfg = lcfg
        report_lines.append(f"- {name}: {len(sub)} rows, bbox {bbox}")

    # counts of the release (SPEC section 12 item 6: 242 / 89 / 3602)
    counts = {k: len(v) for k, v in levels.items()}
    report_lines.append(f"- unit counts: {counts}")
    expected = rel_cfg.get("expected_counts")
    if expected:
        wrong = {k: (counts.get(k), v) for k, v in expected.items() if counts.get(k) != v}
        if wrong:
            raise GateError("G4", f"unit counts differ from expected_counts of the release yaml (found, expected): {wrong}")
        report_lines.append(f"- unit counts equal expected_counts of the release yaml: {dict(expected)}")
    contested_checks = check_contested_areas(ctx, levels, report_lines) if "contested_areas" in file_map.values() else None
    ver_cfg = compute_verification(cfg, rel_cfg, registry, levels, ctx, report_lines)
    check_registry_unit_types(rel_cfg, registry, ctx, report_lines)

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
    license_checked = False
    for key, value in (rel_cfg.get("reference_files") or {}).items():
        if key not in REFERENCE_DESCRIPTIONS:
            raise GateError("G6", f"reference_files: unknown key {key!r}; known keys: {sorted(REFERENCE_DESCRIPTIONS)}")
        p, publish_as, sha = _reference_path(value, ctx, key)
        if sha is not None:
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            if got != sha.lower():
                raise GateError("G6", f"{key}: SHA-256 of {p.name} is {got}, expected {sha}")
            license_checked = license_checked or key == "license_unicode"
            report_lines.append(f"- {publish_as}: SHA-256 equals {sha[:8]}... (checked)")
        dst = out / publish_as
        check_reference_text(p)
        shutil.copyfile(p, dst)
        hash_input(ctx, p)
        extra.append({"file": dst, "description": REFERENCE_DESCRIPTIONS[key]})

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
    if contested_checks is not None:
        checks.append({"id": "contested_areas_valid", "description": contested_checks})
    if license_checked:
        checks.append({"id": "license_notice_sha256", "description":
                       "The Unicode License v3 notice published with the release was compared by SHA-256 with the LICENSE file of Unicode CLDR release-48-2."})
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
    meta = assemble_meta_boundaries(ver_cfg, ctx, sources, fields, coverage, checks, display)
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


def check_registry_frozen_rows(rel_cfg: dict[str, Any], report_lines: list[str]) -> None:
    """G6: rows of the registry that were in the previous release stay identical to it (ARCH6, 17 October).

    `registry_frozen_rows.reference` is the registry of the previous release (for version 0.1.0: the file of commit
    227ce5c). Every row of it must stand in the registry of this release as it is, text for text (line endings are
    not compared), except the rows listed in `registry_frozen_rows.changed_rows` ("ISO3|LEVEL"); those are
    changed on purpose and must be named in the release file.
    """
    frozen = rel_cfg["registry_frozen_rows"]
    ref_path = resolve_path(frozen["reference"])
    reg_path = resolve_path(rel_cfg["boundaries"]["registry"])
    for p in (ref_path, reg_path):
        if not p.exists():
            raise GateError("G6", f"registry_frozen_rows: file is missing: {p}")
    _, ref_header, ref_records = read_records(ref_path)
    _, header, records = read_records(reg_path)
    if header != ref_header:
        raise GateError("G6", f"registry_frozen_rows: the header of {reg_path.name} differs from the previous release")
    changed = set(frozen.get("changed_rows") or [])
    ref_keys = {k for k, *_ in ref_records}
    if changed - ref_keys:
        raise GateError("G6", f"registry_frozen_rows.changed_rows names rows that are not in the reference: {sorted(changed - ref_keys)}")
    by_key: dict[str, list[tuple[str, list[str]]]] = {}
    for key, norm, cells, _ in records:
        by_key.setdefault(key, []).append((norm, cells))
    problems: list[str] = []
    for key, ref_norm, ref_cells, _ in ref_records:
        if key in changed:
            continue
        found = by_key.get(key, [])
        if len(found) != 1:
            problems.append(f"{key}: {len(found)} rows in the registry, expected 1")
        elif found[0][0] != ref_norm:
            cols = [h for h, a, b in zip(header, found[0][1], ref_cells) if a != b]
            problems.append(f"{key}: differs from the previous release in column(s) {', '.join(cols) or 'line breaks'}")
    if problems:
        raise GateError("G6", "registry rows of the previous release are not identical to it (run "
                              "patch_registry_frozen_v020.py, or list the row in registry_frozen_rows.changed_rows): "
                              + "; ".join(problems))
    kept = len(ref_keys) - len(changed)
    report_lines.append(f"- Registry: {kept} rows of the previous release are identical to {ref_path.name}"
                        + (f"; changed on purpose: {', '.join(sorted(changed))}" if changed else ""))


def check_reference_text(path: Path) -> None:
    """G7: a reference file of the boundaries release is public text; Cyrillic is not allowed in it."""
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        m = CYRILLIC_REGEX.search(line)
        if m:
            raise GateError("G7", f"Cyrillic in the public reference file {path.name}, line {n}, "
                                  f"near: {line[max(0, m.start() - 30):m.start() + 30]!r}")


def _reference_path(value: Any, ctx: BuildContext, key: str) -> tuple[Path, str, str | None]:
    """Reference file: (path, name in the release, expected SHA-256 or None).

    `value` is a path, or a mapping with `path` (or `find` + `name` to search a folder for a file by its SHA-256),
    optional `publish_as` and optional `sha256`. The registry etc. live in the repository, the rest in the
    BND output.
    """
    sha = None
    publish_as = None
    if isinstance(value, dict):
        sha = value.get("sha256")
        publish_as = value.get("publish_as")
        if "find" in value:
            if not sha:
                raise GateError("G6", f"{key}: `find` needs `sha256`")
            folder = resolve_path(value["find"])
            pattern = value.get("name", "*")
            hits = [q for q in sorted(folder.rglob(pattern)) if q.is_file()
                    and hashlib.sha256(q.read_bytes()).hexdigest() == sha.lower()] if folder.exists() else []
            if not hits:
                raise GateError("G6", f"{key}: no file named {pattern} with SHA-256 {sha} under {folder}")
            path = hits[0]
        else:
            path = resolve_path(value["path"]) if str(value["path"]).startswith(("boundaries", "D:", "d:")) \
                else resolve_path(value["path"], ctx.boundaries.root)
    else:
        path = resolve_path(value, ctx.boundaries.root) if not str(value).startswith(("boundaries", "D:", "d:")) else resolve_path(value)
    if not path.exists():
        raise GateError("G6", f"reference file is missing: {path}")
    return path, publish_as or path.name, sha


def join_contested_columns(ctx: BuildContext, rel_cfg: dict[str, Any], report_lines: list[str]) -> None:
    """Add the columns of contested_areas.csv that the CODE-BND layer does not carry (frame_unit_ids, sources, checks).

    The CODE-BND layer has area_id, name, controlled_by, claimed_by, control_since, label and the geometry. The other
    columns come from the reference file by area_id. The areas of the two files must be the same, and the columns
    that both have must be equal; otherwise the build stops (G4).
    """
    key = "display/contested_areas.parquet"
    gdf = ctx.boundaries.read(key)
    ref_value = (rel_cfg.get("reference_files") or {}).get("contested_areas")
    if not ref_value:
        raise GateError("G6", "contested_areas_columns_from_reference needs reference_files.contested_areas")
    path, _, _ = _reference_path(ref_value, ctx, "contested_areas")
    hash_input(ctx, path)
    ref = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if "area_id" not in ref.columns or ref["area_id"].duplicated().any():
        raise GateError("G4", f"{path.name}: area_id is missing or not unique")
    if sorted(ref["area_id"]) != sorted(gdf["area_id"]):
        raise GateError("G4", f"contested_areas: areas of the layer {sorted(gdf['area_id'])} differ from {path.name} {sorted(ref['area_id'])}")
    ref = ref.set_index("area_id")
    for col in (c for c in gdf.columns if c in ref.columns):
        bad = [a for a, v in zip(gdf["area_id"], gdf[col].astype(str)) if ref.at[a, col] != v]
        if bad:
            raise GateError("G4", f"contested_areas: column {col} of the layer differs from {path.name} in {bad}")
    added = [c for c in ref.columns if c not in gdf.columns]
    for col in added:
        gdf[col] = gdf["area_id"].map(ref[col])
    ctx.boundaries._cache[key] = gdf
    report_lines.append(f"- contested_areas: columns {added} added from {path.name} by area_id; shared columns are equal")


def check_contested_areas(ctx: BuildContext, levels: dict[str, gpd.GeoDataFrame], report_lines: list[str]) -> str:
    """Checks of the contested_areas layer; returns the text for automated_checks (what was really checked)."""
    gdf = ctx.boundaries.read("display/contested_areas.parquet")
    need = ["area_id", "frame_unit_ids", "controlled_by", "claimed_by"]
    absent = [c for c in need if c not in gdf.columns]
    if absent:
        raise GateError("G4", f"contested_areas: columns {absent} are missing; found {list(gdf.columns)}: stop and ask [ARCH]/[CODE-BND]")
    if gdf["area_id"].duplicated().any():
        raise GateError("G4", "contested_areas: area_id is not unique")
    frame = pd.concat([levels[k][["unit_id", "geometry"]] for k in ("adm0", "adm1", "adm2")], ignore_index=True)
    geom = dict(zip(frame["unit_id"], frame["geometry"]))
    countries = set(levels["adm0"]["iso3"])
    for _, row in gdf.iterrows():
        ids = [x.strip() for x in str(row["frame_unit_ids"]).split(";") if x.strip()]
        missing = [i for i in ids if i not in geom]
        if not ids or missing:
            raise GateError("G4", f"contested_areas {row['area_id']}: frame units not found in the release: {missing or 'none named'}")
        for col in ("controlled_by", "claimed_by"):
            codes = [x.strip() for x in str(row[col]).split(";") if x.strip()]
            bad = [c for c in codes if c not in countries]
            if not codes or bad:
                raise GateError("G4", f"contested_areas {row['area_id']}: {col} is not an ADM0 iso3 of the release: {bad or 'empty'}")
        union = unary_union([geom[i] for i in ids])
        diff = gpd.GeoSeries([row.geometry.symmetric_difference(union)], crs=4326).to_crs(6933).area.iloc[0] / 1e6
        if diff > 0.01:
            raise GateError("G4", f"contested_areas {row['area_id']}: geometry differs from the union of its frame units by {diff:.3f} km2")
        report_lines.append(f"- contested_areas {row['area_id']}: {len(ids)} frame unit(s), geometry equals their union (difference {diff:.4f} km2)")
    rows = list(gdf.sort_values("area_id")["geometry"])
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            ov = gpd.GeoSeries([rows[i].intersection(rows[j])], crs=4326).to_crs(6933).area.iloc[0] / 1e6
            if ov > 0.01:
                raise GateError("G4", f"contested_areas: two areas overlap by {ov:.3f} km2")
    return (f"Every frame unit named by the {len(gdf)} contested area(s) exists in the release; the geometry of each area equals "
            f"the union of its frame units; the areas do not overlap; the states are countries of the ADM0 layer.")


def compute_verification(cfg: dict[str, Any], rel_cfg: dict[str, Any], registry: pd.DataFrame,
                         levels: dict[str, gpd.GeoDataFrame], ctx: BuildContext, report_lines: list[str]) -> dict[str, Any]:
    """verification.sample_share and levels.agent_sample from the registry of the release (SPEC_BND 3 item 3c).

    Countries counted: those with verified ADM1 that are not in `exclude_iso3` (the countries of the earlier release).
    A country is in the sample when its `verified_against` holds a verdict confirmed, disputed or refer_arch.
    """
    vcfg = rel_cfg.get("verification_from_registry")
    if not vcfg:
        return cfg
    exclude = set(vcfg.get("exclude_iso3", []))
    reg = registry[registry["level"].map(Boundaries.norm_level) == "ADM1"]
    reg = reg[reg["verified"].astype(str).str.strip().str.lower() == "true"]
    new = reg[~reg["iso3"].isin(exclude)]
    n_new = new["iso3"].nunique()
    if vcfg.get("expected_countries") is not None and n_new != vcfg["expected_countries"]:
        raise GateError("G12", f"registry: {n_new} verified ADM1 countries outside {sorted(exclude)}, expected {vcfg['expected_countries']}")
    verdicts: dict[str, str] = {}
    for _, row in new.iterrows():
        m = VERDICT_REGEX.findall(str(row["verified_against"]))
        if m:
            verdicts[row["iso3"]] = m[-1].lower()
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in ("confirmed", "disputed", "refer_arch")}
    n_units = int(levels["adm1"]["iso3"].isin(verdicts).sum())
    total = sum(len(v) for v in levels.values())
    share = round(len(verdicts) / n_new, 3) if n_new else 0.0
    units_share = round(n_units / total, 3)
    line = (f"- verification sample: {len(verdicts)} of {n_new} new countries with a verdict {counts}; "
            f"{n_units} ADM1 units of {total}; sample_share {share}, agent_sample {units_share}")
    report_lines.append(line)
    exp = vcfg.get("expected_verdicts")
    if exp and (exp != counts or vcfg.get("expected_units") not in (None, n_units)):
        msg = (f"verification sample differs from the expected one: verdicts {counts}, units {n_units}; "
               f"expected {exp}, units {vcfg.get('expected_units')}")
        if ctx.channel == "final":
            raise GateError("G12", msg)
        ctx.report.warn(msg + " (a stop in final)")
    out = copy.deepcopy(cfg)
    out["verification"] = copy.deepcopy(cfg["verification"])
    out["verification"]["levels"] = {**cfg["verification"]["levels"], "agent_sample": units_share}
    out["verification"]["sample_share"] = {"adm1_countries_official_list": share}
    return out


def check_registry_unit_types(rel_cfg: dict[str, Any], registry: pd.DataFrame, ctx: BuildContext,
                              report_lines: list[str]) -> None:
    """The two numbers of known_gaps item 11 (types of first-level units) are counted from the registry.

    Rows counted: ADM1 rows of countries outside `exclude_iso3` (the countries of the earlier release).
    multi_type = a "/" in unit_type_local or unit_type_en; empty = both type cells empty. A difference from the
    numbers of the release yaml is a warning in dev and a stop in final (the numbers stand in the public text).
    """
    tcfg = rel_cfg.get("registry_unit_types")
    if not tcfg:
        return
    exclude = set(tcfg.get("exclude_iso3") or (rel_cfg.get("verification_from_registry") or {}).get("exclude_iso3", []))
    reg = registry[registry["level"].map(Boundaries.norm_level) == "ADM1"]
    reg = reg[~reg["iso3"].isin(exclude)]
    loc = reg["unit_type_local"].fillna("").astype(str).str.strip()
    eng = reg["unit_type_en"].fillna("").astype(str).str.strip()
    found = {"multi_type": int((loc.str.contains("/", regex=False) | eng.str.contains("/", regex=False)).sum()),
             "empty": int(((loc == "") & (eng == "")).sum())}
    report_lines.append(f"- unit types in the registry ({len(reg)} countries): {found['multi_type']} with more than one type "
                        f"(a \"/\"), {found['empty']} with no type; the public text says {tcfg['multi_type']} and {tcfg['empty']}")
    wrong = {k: (found[k], tcfg[k]) for k in found if found[k] != tcfg[k]}
    if wrong:
        msg = f"numbers of unit types in the registry differ from the text of known_gaps (found, in text): {wrong}"
        if ctx.channel == "final":
            raise GateError("G12", msg)
        ctx.report.warn(msg + " (a stop in final)")


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
                # the schema forbids a path in `file`: for "Unicode CLDR release-48-2: common/subdivisions/en.xml" keep the file name
                name = re.split(r"[\\/]", product.split(": ")[-1])[-1] if "CLDR" in product else product
                inputs.append({"file": name, "bytes": None, "sha256": item["sha256"]})
        if not inputs:
            raise GateError("G6", f"{src['source_id']}: no upstream record with a SHA-256 in the boundaries meta.json")
        src["inputs"] = sorted(inputs, key=lambda x: x["file"])
        if str(src["retrieved_at"]) == "bnd_meta":
            dates = sorted({str(i.get(k))[:10] for i in bnd_sources if i.get("publisher") == src["publisher"]
                            and any(m in str(i.get("product", "")) for m in match)
                            for k in ("retrieved_at", "downloaded_at", "date", "retrieved") if i.get(k)})
            if len(dates) != 1:
                raise GateError("G6", f"{src['source_id']}: retrieved_at: bnd_meta needs exactly one download day in the "
                                      f"boundaries meta.json, found {dates}: tell [ARCH]")
            src["retrieved_at"] = dates[0]
        src["retrieved_at"] = str(src["retrieved_at"])
        src["current_through"] = None if src["current_through"] is None else str(src["current_through"])
        for key in ("checked_at",):
            if key in src.get("rights_basis", {}):
                src["rights_basis"][key] = str(src["rights_basis"][key])
        result.append(src)
    return result
