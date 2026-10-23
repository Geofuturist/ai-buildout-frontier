"""Build one release (abf-layers or abf-boundaries) into a local folder.

Run command (from the repository root, Windows):
    python scripts\\publish\\build_release.py --release releases\\abf-layers-v0.1.0.yaml --out "D:\\GISData\\release" --channel dev

What it does: reads the release yaml, builds the data files, meta.json files and
the tile inputs, runs the gates G1-G7 and G10-G13, and writes release_report.md,
build_log.json, build_plan.json and zenodo_files.txt. It does not touch R2.
Tiles and manifest.json are made later by the workflow "Build tiles and finalize".
"""
from __future__ import annotations

import argparse
import logging
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boundaries_build
import check_dc_phrases
import layer_build
from common import (
    DOI_REGEX,
    SCHEMA_DIR,
    GateError,
    Report,
    dump_yaml_value,
    find_cyrillic,
    find_placeholders,
    load_yaml,
    p9_value_hits,
    P9_VALUE_FIELDS,
    read_json,
    resolve_path,
    setup_logging,
    sha256_file,
    utc_iso,
    write_json,
)
from layer_build import Boundaries, BuildContext, LayerOutput

log = logging.getLogger("publish.build")
PLAN_NAME = "build_plan.json"
MARKER = ".abf_release_dir"   # written first, so a failed build can be cleaned up by the next run


def validate_meta(meta: dict[str, Any]) -> None:
    """G1: meta.json against schemas/meta.schema.json."""
    import jsonschema

    schema = read_json(SCHEMA_DIR / "meta.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(meta), key=lambda e: list(e.absolute_path))
    if errors:
        text = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in errors[:8])
        raise GateError("G1", f"{meta.get('layer_id')}: meta.json does not match the schema: {text}")


def load_boundaries(rel: dict[str, Any]) -> Boundaries:
    root = resolve_path(rel["boundaries"]["dir"])
    reg_path = resolve_path(rel["boundaries"]["registry"])
    if not root.exists():
        raise GateError("G4", f"boundaries output folder not found: {root}")
    if not reg_path.exists():
        raise GateError("G12", f"boundary registry not found: {reg_path}")
    registry = pd.read_csv(reg_path, dtype=str, keep_default_na=False)
    overrides = None
    ov_value = rel["boundaries"].get("name_overrides")
    if ov_value:
        ov_path = resolve_path(ov_value)
        if not ov_path.exists():
            raise GateError("G12", f"name overrides file not found: {ov_path}")
        overrides = pd.read_csv(ov_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        absent = [c for c in ("unit_id", "name_source", "name") if c not in overrides.columns]
        if absent:
            raise GateError("G12", f"{ov_path.name} has no columns {absent}; found {list(overrides.columns)}")
        for c in ("name_source", "name"):
            overrides[c] = overrides[c].str.strip()
        overrides["unit_id"] = overrides["unit_id"].str.strip()
    return Boundaries(root=root, registry=registry, name_overrides=overrides)


def registry_report(boundaries: Boundaries, report: Report) -> None:
    """Section 4 of the handoff: verification columns of every registry row."""
    cols = [c for c in ("iso3", "level", "verified", "verified_by", "verified_at", "verified_against")
            if c in boundaries.registry.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in boundaries.registry.iterrows():
        lines.append("| " + " | ".join(str(row[c]).replace("|", "/") for c in cols) + " |")
    report.section("Boundary registry: verification", lines)


def scan_text_values(layer: LayerOutput, report: Report) -> None:
    """G3 (text part): P9 words in the provenance fields are listed in the report, not a stop."""
    path = layer.files["csv"] if "csv" in layer.files else None
    if path is None:
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    hits: dict[str, list[str]] = {}
    for col in df.columns:
        if col not in P9_VALUE_FIELDS:
            continue
        vals = pd.Series(df[col].unique())
        found = p9_value_hits([v for v in vals if v])
        if found:
            hits[col] = found[:20]
    if hits:
        report.section("P9 words in text values (not a stop)", [f"- {layer.layer_id}.{c}: {v}" for c, v in hits.items()])


def check_inputs_unchanged(ctx: BuildContext) -> None:
    """G6: SHA-256 of every input recomputed at the end of the build."""
    for key, rec in ctx.input_hashes.items():
        again = sha256_file(Path(key))
        if again != rec["sha256"]:
            raise GateError("G6", f"input changed during the build: {key}")
    ctx.report.note(f"G6: {len(ctx.input_hashes)} input files re-hashed, all unchanged")


def plan_layer(lo: LayerOutput, out: Path, extra: list[dict[str, Any]], tiles_file: str) -> dict[str, Any]:
    """One entry of build_plan.json (the manifest layer without the tile file hash)."""
    files = {fmt: p.name for fmt, p in lo.files.items()}
    entry = {
        "layer_id": lo.layer_id, "title": lo.title, "domain": lo.domain, "level": lo.level,
        "bbox": lo.bbox,
        "meta": lo.meta_path.name,
        "files": files,
        "extra_files": extra,
        "tiles": {"file": tiles_file, "source_layer": lo.source_layer or lo.layer_id,
                  "geometry_type": lo.geometry_type, "minzoom": int(lo.tile_cfg.get("minzoom", 0)),
                  "maxzoom": int(lo.tile_cfg.get("maxzoom", 10)), "fields": lo.tile_fields},
    }
    home_bbox = (lo.meta.get("display") or {}).get("home_bbox")  # copied as is from meta.json (SPEC_META 6 item 23)
    if home_bbox is not None:
        entry["home_bbox"] = home_bbox
    return entry


def run_cross_checks(checks: list[dict[str, Any]], out: Path, boundaries: Boundaries, report: Report) -> None:
    """Checks between the files of one release (abf-dc): references into a layer, counts that add up (G4).

    kind refs_in_layer: every id in column `column` of `file` (several ids separated by `separator`, empty cells
        skipped) is a value of `layer_column` of the layer `layer`.
    kind counts_match: for every country, the count columns of the count layer equal the numbers of records of the
        point layer; `columns` maps a count column to None (all records) or to {column: value} of the point layer
        (an empty value matches empty cells).
    """
    for chk in checks:
        kind = chk["kind"]
        if kind == "refs_in_layer":
            df = pd.read_csv(out / chk["file"], dtype=str, keep_default_na=False)
            ids = {part.strip() for v in df[chk["column"]] for part in str(v).split(chk.get("separator", ";")) if part.strip()}
            layer = pd.read_csv(out / f"{chk['layer']}.csv", dtype=str, keep_default_na=False, usecols=[chk["layer_column"]])
            missing = sorted(ids - set(layer[chk["layer_column"]]))
            if missing:
                raise GateError("G4", f"{chk['file']}.{chk['column']} refers to records that are not in {chk['layer']}: {missing[:5]}")
            report.note(f"cross-check: {len(ids)} ids of {chk['file']}.{chk['column']} exist in {chk['layer']}")
        elif kind == "counts_match":
            counts = pd.read_csv(out / f"{chk['count_layer']}.csv", dtype=str, keep_default_na=False)
            points = pd.read_csv(out / f"{chk['point_layer']}.csv", dtype=str, keep_default_na=False)
            _, to_iso = layer_build.adm0_codes(BuildContextStub(boundaries))
            counts["_iso"] = counts[chk["unit_column"]].map(to_iso)
            if counts["_iso"].isna().any():
                raise GateError("G4", f"{chk['count_layer']}: unit_id values that are not countries of the boundaries release")
            for col, cond in chk["columns"].items():
                sub = points
                if cond:
                    ((cc, vv),) = cond.items()
                    sub = points[points[cc] == str(vv)]
                have = sub.groupby(chk["point_iso_column"]).size()
                want = pd.to_numeric(counts.set_index("_iso")[col], errors="raise").astype(int)
                joined = pd.concat([want.rename("layer"), have.rename("points")], axis=1).fillna(0).astype(int)
                bad = joined[joined["layer"] != joined["points"]]
                if len(bad):
                    raise GateError("G4", f"{chk['count_layer']}.{col} differs from the records of {chk['point_layer']} "
                                          f"for {len(bad)} countries, for example {bad.head(3).to_dict('index')}")
            report.note(f"cross-check: {len(chk['columns'])} count columns of {chk['count_layer']} equal the records of {chk['point_layer']} for every country")
        else:
            raise GateError("G2", f"unknown cross_check kind {kind!r}")


class BuildContextStub:
    """Just enough of the build context for layer_build.adm0_codes (only .boundaries is read)."""

    def __init__(self, boundaries: Boundaries) -> None:
        self.boundaries = boundaries


def run_phrase_check(cfg: dict[str, Any], channel: str, report: Report) -> None:
    """Phrases of the abf-dc texts against the saved source pages (check_dc_phrases.py). A stop in final, a warning in dev."""
    pages = resolve_path(cfg["pages"])
    readme = resolve_path(cfg["geonames_readme"]) if cfg.get("geonames_readme") else None
    lines, not_found, problems = check_dc_phrases.run_check(pages, readme, resolve_path(cfg.get("layers", "layers")))
    report.section("Phrases of the abf-dc texts against the saved pages", [f"- {l}" for l in lines if not l.startswith("         ")])
    if not_found or problems:
        msg = f"phrase check (RES_texts_DC section 10): missing {not_found}; problems {problems}"
        if channel == "final":
            raise GateError("G13", msg)
        report.warn(msg + " (a warning in dev, a stop in final)")


def run(args: argparse.Namespace) -> int:
    started = time.time()
    rel_path = resolve_path(args.release)
    rel = load_yaml(rel_path)
    dataset, version, tag = rel["dataset"], str(rel["version"]), rel["tag"]
    channel = args.channel
    report = Report(f"Release report {tag} ({channel})")

    # --- G11 and dates
    doi = rel.get("doi") or None
    if channel == "final":
        if not doi or not DOI_REGEX.match(str(doi)):
            raise GateError("G11", f"final channel needs doi like 10.5281/zenodo.<number>, got {doi!r}")
    else:
        doi = None
    built_at = args.built_at or rel.get("built_at")
    if not built_at:
        built_at = utc_iso(datetime.now(timezone.utc).replace(microsecond=0))
        if channel == "final":
            dump_yaml_value(rel_path, "built_at", f'"{built_at}"')
            report.note(f"built_at frozen in {rel_path.name}: {built_at}")
    built_at = str(built_at)
    published_at = str(rel.get("published_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    out = resolve_path(args.out) / tag
    if out.exists() and any(out.iterdir()):
        if not ((out / PLAN_NAME).exists() or (out / MARKER).exists()):
            raise GateError("paths", f"{out} is not empty and is not a release folder of this script; choose another --out")
        keep_manifest = out / "manifest.json"
        saved = keep_manifest.read_bytes() if keep_manifest.exists() else None
        shutil.rmtree(out)
        out.mkdir(parents=True)
        if saved is not None:
            (out / "manifest.json").write_bytes(saved)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("made by build_release.py\n", encoding="utf-8")
    tmp_dir = out.parent / f"_tmp_{tag}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    boundaries = load_boundaries(rel)
    registry_report(boundaries, report)
    overrides = dict(item.split("=", 1) for item in (args.override or []))
    ctx = BuildContext(release=rel, channel=channel, out_dir=out, built_at=built_at, published_at=published_at,
                       doi=doi, boundaries=boundaries, report=report, overrides=overrides, tmp_dir=tmp_dir)

    plan_layers: list[dict[str, Any]] = []
    plan_extra: list[dict[str, Any]] = []
    archives: dict[str, dict[str, Any]] = {}
    tile_builds: list[dict[str, Any]] = []
    metas: list[tuple[Path, dict[str, Any]]] = []
    all_layers: list[LayerOutput] = []
    check_lists: dict[str, list[str]] = {}

    if dataset == "abf-boundaries":
        cfg = load_yaml(resolve_path(rel["layers"][0]))
        bo = boundaries_build.build_boundaries(cfg, ctx, rel)
        report.section("Boundaries", bo.report_lines)
        metas.append((bo.meta_path, bo.meta))
        for f in bo.extra_files:
            plan_extra.append({"path": f["file"].name, "description": f["description"]})
        for lo in bo.layers:
            plan_layers.append(plan_layer(lo, out, [], "boundaries.pmtiles"))
        tile_builds.append(bo.tile_build)
        all_layers += bo.layers
        check_lists[cfg["layer_id"]] = [c["id"] for c in bo.meta["verification"]["automated_checks"]]
    else:
        for layer_yaml in rel["layers"]:
            cfg = load_yaml(resolve_path(layer_yaml))
            if cfg.get("publish") is False:
                raise GateError("P9", f"{cfg['layer_id']}: the layer has publish: false but is listed in the release")
            if cfg["level"] == "line":
                lo = layer_build.build_line_layer(cfg, ctx)
            elif cfg["level"] == "point":
                lo = layer_build.build_point_layer(cfg, ctx)
            else:
                lo = layer_build.build_adm_layer(cfg, ctx)
            if cfg["domain"] == "dc" and cfg["level"] not in ("point", "ADM0"):
                raise GateError("G3b", f"{cfg['layer_id']}: only point layers and the world ADM0 count layer are supported for the domain dc")
            metas.append((lo.meta_path, lo.meta))
            all_layers.append(lo)
            plan_layers.append(plan_layer(lo, out, lo.extra_files, f"{lo.layer_id}.pmtiles"))
            tile_builds.append({**lo.tile_build})
            for a in lo.archives:
                archives[a["file"].name] = a
            check_lists[lo.layer_id] = [c["id"] for c in lo.meta["verification"]["automated_checks"]]
            scan_text_values(lo, report)

    # --- G3b across the release: not more than one layer of the domain dc carries power fields
    power_layers = [lo.layer_id for lo in all_layers if lo.domain == "dc" and lo.carries_power]
    if len(power_layers) > 1:
        raise GateError("G3b", f"more than one layer of the domain dc carries power fields: {power_layers}")
    # the class thresholds of the dc layers of one release are common (ADR section 11)
    breaks = {lo.layer_id: tuple((lo.meta.get("display") or {}).get("size_breaks") or ()) for lo in all_layers
              if lo.domain == "dc" and (lo.meta.get("display") or {}).get("size_breaks")}
    if len(set(breaks.values())) > 1:
        raise GateError("G3b", f"the dc layers of the release have different display.size_breaks: {breaks}")
    if rel.get("cross_checks"):
        run_cross_checks(rel["cross_checks"], out, boundaries, report)
    if rel.get("phrase_check"):
        run_phrase_check(rel["phrase_check"], channel, report)

    # --- meta.json: G7, G1, write
    for path, meta in metas:
        cyr = find_cyrillic(meta)
        if cyr:
            raise GateError("G7", f"{meta['layer_id']}: Cyrillic in public text at {cyr}")
        holes = find_placeholders(meta)
        if holes:
            msg = f"{meta['layer_id']}: unfilled places in public text (G13): " + "; ".join(f"{p} has {tok}" for p, tok in holes)
            if channel == "final":
                raise GateError("G13", msg)
            report.warn(msg + " (allowed in dev, a stop in final)")
        validate_meta(meta)
        write_json(path, meta)

    check_inputs_unchanged(ctx)

    source_archives = [{"path": f"sources/{name}", "description": a["description"]} for name, a in sorted(archives.items())]
    plan = {
        "schema_version": "abf-plan-1.0",
        "dataset": dataset, "version": version, "tag": tag, "channel": channel,
        "doi": doi, "published_at": published_at, "boundary_release": rel.get("boundary_release"),
        "base_path": f"{'dev/' if channel == 'dev' else ''}{dataset}/v{version}/",
        "layers": plan_layers, "extra_files": plan_extra, "source_archives": source_archives,
        "tile_builds": tile_builds,
    }
    write_json(out / PLAN_NAME, plan)

    # --- zenodo_files.txt (no PMTiles)
    names: list[str] = []
    for lo in all_layers:
        names += [p.name for p in lo.files.values()]
        names += [e["path"] for e in lo.extra_files]
    names += sorted({p.name for p, _ in metas})
    names += [e["path"] for e in plan_extra]
    names += [a["path"] for a in source_archives]
    names.append("manifest.json  (after verify_release.py --save-manifest)")
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    (out / "zenodo_files.txt").write_text("\n".join(seen) + "\n", encoding="utf-8", newline="\n")

    # --- report and log
    report.section("automated_checks per layer", [f"- {k}: {', '.join(v)}" for k, v in check_lists.items()])
    report.section("Files", [f"- {p.relative_to(out)}: {p.stat().st_size} bytes"
                             for p in sorted(out.rglob("*")) if p.is_file()])
    (out / "release_report.md").write_text(report.to_markdown(), encoding="utf-8", newline="\n")
    log_obj = {
        "tag": tag, "channel": channel, "built_at": built_at,
        "elapsed_seconds": round(time.time() - started, 1),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": _versions(),
        "inputs": {k: v for k, v in sorted(ctx.input_hashes.items())},
        "overrides": overrides,
        "boundaries_dir": str(boundaries.root),
        "release_yaml": str(rel_path),
    }
    write_json(out / "build_log.json", log_obj)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    log.info("Done: %s. Warnings: %d. Report: %s", tag, len(report.warnings), out / "release_report.md")
    return 0


def _versions() -> dict[str, str]:
    out = {}
    for name in ("pandas", "geopandas", "pyarrow", "pyogrio", "shapely", "pyproj", "jsonschema"):
        try:
            from importlib.metadata import version as pkg_version
            out[name] = pkg_version(name)
        except Exception:  # noqa: BLE001 - package missing or without metadata
            out[name] = "not installed"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one release of the publication.")
    parser.add_argument("--release", required=True, help=r"releases\<tag>.yaml")
    parser.add_argument("--out", required=True, help="folder for releases; a subfolder <tag> is made")
    parser.add_argument("--channel", choices=["dev", "final"], required=True)
    parser.add_argument("--override", action="append", metavar="LAYER_ID=PATH",
                        help="use another input table for one layer (swap of the input edition)")
    parser.add_argument("--built-at", help="fix built_at (UTC, YYYY-MM-DDTHH:MM:SSZ), for repeat-build tests")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        return run(args)
    except GateError as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
