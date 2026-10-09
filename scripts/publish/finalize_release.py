"""Build tiles, compose manifest.json, publish to the public bucket (runs in GitHub Actions).

Run command (normally by the workflow "Build tiles and finalize"; by hand for tests):
    python scripts/publish/finalize_release.py --dataset abf-layers --version 0.1.0 --channel dev --work work --tippecanoe tippecanoe

Steps: download the staged release -> Tippecanoe -> G8 -> manifest.json (G1, G11) ->
copy only the files of the manifest to the public bucket with the headers of SPEC 4.1
(G9: manifest.json last) -> manifest/dev.json (channel dev) -> clean staging ->
copy CSV, meta and manifest to --git-out (channel final).
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DOI_REGEX, SCHEMA_DIR, GateError, file_ref, read_json, setup_logging, sha256_file, utc_iso, write_json
from r2io import StoreError, open_store

log = logging.getLogger("publish.finalize")
PMTILES_LIMIT_BYTES = 512 * 1000 * 1000  # G8, P12


def tippecanoe_version(binary: str) -> str:
    r = subprocess.run([binary, "--version"], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def build_pmtiles(binary: str, work: Path, spec: dict[str, Any]) -> Path:
    """Run Tippecanoe for one tile build of the plan."""
    out = work / spec["output"]
    if out.exists():
        out.unlink()
    cmd = [binary, "-o", str(out), "--force", f"-Z{spec['minzoom']}", f"-z{spec['maxzoom']}",
           "-P", "--no-progress-indicator"]
    cmd += list(spec.get("args", []))
    for item in spec["inputs"]:
        layer: dict[str, Any] = {"file": str(work / item["input"]), "layer": item["source_layer"]}
        if "minzoom" in item:
            layer["minzoom"] = int(item["minzoom"])
        if "maxzoom" in item:
            layer["maxzoom"] = int(item["maxzoom"])
        cmd += ["-L", json.dumps(layer, separators=(",", ":"))]
    log.info("tippecanoe: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise GateError("tiles", f"tippecanoe failed ({r.returncode}) for {spec['output']}: {r.stderr[-1500:]}")
    log.info("%s: %.1f MB", out.name, out.stat().st_size / 1e6)
    return out


def check_pmtiles_header(path: Path) -> None:
    with path.open("rb") as fh:
        head = fh.read(8)
    if len(head) < 8 or head[:7] != b"PMTiles" or head[7] != 3:
        raise GateError("tiles", f"{path.name} is not a PMTiles v3 file")


def compose_manifest(plan: dict[str, Any], work: Path) -> dict[str, Any]:
    """manifest.json (abf-manifest-1.0) from the plan and the real files."""
    layers = []
    for lp in plan["layers"]:
        files = {fmt: file_ref(work / name) for fmt, name in lp["files"].items()}
        tiles = lp["tiles"]
        files["pmtiles"] = file_ref(work / tiles["file"])
        layers.append({
            "layer_id": lp["layer_id"], "title": lp["title"], "domain": lp["domain"], "level": lp["level"],
            "bbox": lp["bbox"], "meta": file_ref(work / lp["meta"]),
            "files": {k: files[k] for k in ("parquet", "geojson.gz", "csv", "pmtiles") if k in files},
            "extra_files": [{**file_ref(work / e["path"]), "description": e["description"]} for e in lp.get("extra_files", [])],
            "tiles": tiles,
        })
    return {
        "schema_version": "abf-manifest-1.0",
        "dataset": plan["dataset"], "version": plan["version"], "tag": plan["tag"],
        "doi": plan["doi"], "published_at": plan["published_at"],
        "boundary_release": plan.get("boundary_release"),
        "base_path": plan["base_path"],
        "layers": layers,
        "extra_files": [{**file_ref(work / e["path"]), "description": e["description"]} for e in plan.get("extra_files", [])],
        "source_archives": [{**file_ref(work / a["path"], a["path"]), "description": a["description"]}
                            for a in plan.get("source_archives", [])],
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    import jsonschema

    schema = read_json(SCHEMA_DIR / "manifest.schema.json")
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.absolute_path))
    if errors:
        text = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in errors[:8])
        raise GateError("G1", f"manifest.json does not match the schema: {text}")


def manifest_files(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every file of the manifest: path -> {bytes, sha256}. Only these go to the public bucket."""
    out: dict[str, dict[str, Any]] = {}

    def add(ref: dict[str, Any]) -> None:
        prev = out.get(ref["path"])
        if prev and prev["sha256"] != ref["sha256"]:
            raise GateError("G9", f"two different files with the path {ref['path']}")
        out[ref["path"]] = {"bytes": ref["bytes"], "sha256": ref["sha256"]}

    for layer in manifest["layers"]:
        add(layer["meta"])
        for ref in layer["files"].values():
            add(ref)
        for ref in layer["extra_files"]:
            add(ref)
    for ref in manifest.get("extra_files", []):
        add(ref)
    for ref in manifest["source_archives"]:
        add(ref)
    return out


def publish(manifest: dict[str, Any], work: Path, channel: str) -> None:
    """Copy to the public bucket; manifest.json last (G9)."""
    store = open_store("R2_BUCKET")
    base = manifest["base_path"]
    mkey = base + "manifest.json"
    existing = store.head(mkey)
    new_manifest_bytes = (work / "manifest.json").read_bytes()
    files = manifest_files(manifest)
    complete = existing is not None
    if complete and channel == "final":
        for rel, ref in files.items():
            head = store.head(base + rel)
            if head is None or (head.get("sha256") not in (None, ref["sha256"])) or head["bytes"] != ref["bytes"]:
                raise GateError("G9", f"{base}{rel} differs from the published version: versions are immutable. "
                                      f"Use a new version number")
        remote = store.get_bytes(mkey)
        if remote != new_manifest_bytes:
            raise GateError("G9", f"{mkey} exists and differs from the new manifest: versions are immutable")
        log.info("G9: version %s is already published and identical; nothing to do", base)
        return
    n = 0
    for rel, ref in sorted(files.items()):
        key = base + rel
        head = store.head(key)
        if head and head["bytes"] == ref["bytes"] and head.get("sha256") == ref["sha256"]:
            continue
        log.info("publish %s", key)
        store.put_file(work / rel, key, ref["sha256"])
        n += 1
    store.put_file(work / "manifest.json", mkey, sha256_file(work / "manifest.json"))
    log.info("published %d files and %s (manifest last)", n, mkey)


def update_dev_pointer(manifest: dict[str, Any]) -> None:
    """manifest/dev.json lists both datasets; this run replaces its own entry."""
    store = open_store("R2_BUCKET")
    key = "manifest/dev.json"
    raw = store.get_bytes(key)
    doc = json.loads(raw) if raw else {"schema_version": "abf-latest-1.0", "updated_at": "", "datasets": {}}
    doc["datasets"][manifest["dataset"]] = {"version": manifest["version"], "manifest": manifest["base_path"] + "manifest.json"}
    doc["datasets"] = dict(sorted(doc["datasets"].items()))
    from datetime import datetime, timezone
    doc["updated_at"] = utc_iso(datetime.now(timezone.utc).replace(microsecond=0))
    import jsonschema
    schema = read_json(SCHEMA_DIR / "latest.schema.json")
    if set(doc["datasets"]) != {"abf-layers", "abf-boundaries"}:
        # only one dataset was built so far: check everything except "both datasets present"
        schema["properties"]["datasets"].pop("required", None)
    jsonschema.validate(doc, schema, cls=jsonschema.Draft202012Validator)
    tmp = Path("dev.json.tmp")
    write_json(tmp, doc)
    store.put_file(tmp, key, sha256_file(tmp))
    tmp.unlink()
    missing = {"abf-layers", "abf-boundaries"} - set(doc["datasets"])
    if missing:
        log.warning("manifest/dev.json does not list %s yet (the file should list both datasets)", sorted(missing))


def run(args: argparse.Namespace) -> int:
    tag = f"{args.dataset}-v{args.version}"
    work = Path(args.work).resolve() / tag
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    staging = open_store("R2_STAGING_BUCKET")
    prefix = f"{args.channel}/{tag}/"
    items = list(staging.list(prefix))
    if not items:
        raise GateError("stage", f"nothing in the staging bucket under {prefix}: run upload_r2.py --stage first")
    for item in items:
        staging.get_file(item["key"], work / item["key"][len(prefix):])
    plan = read_json(work / "build_plan.json")
    if plan["channel"] != args.channel or plan["tag"] != tag:
        raise GateError("stage", "build_plan.json does not match the requested dataset, version and channel")
    if args.channel == "final" and not (plan["doi"] and DOI_REGEX.match(plan["doi"])):
        raise GateError("G11", "final channel needs a DOI in the plan")
    if args.channel == "dev" and plan["doi"] is not None:
        raise GateError("G11", "dev channel must have doi = null")

    # staged files: hash check against the staging metadata is done by the store; presence check here
    for lp in plan["layers"]:
        for name in [lp["meta"], *lp["files"].values()]:
            if not (work / name).exists():
                raise GateError("stage", f"file of the plan is missing in staging: {name}")

    version_line = tippecanoe_version(args.tippecanoe)
    log.info("tippecanoe: %s", version_line)
    for spec in plan["tile_builds"]:
        out = build_pmtiles(args.tippecanoe, work, spec)
        check_pmtiles_header(out)
        if out.stat().st_size >= PMTILES_LIMIT_BYTES:
            raise GateError("G8", f"{out.name} is {out.stat().st_size / 1e6:.0f} MB, the limit is 512 MB")

    manifest = compose_manifest(plan, work)
    validate_manifest(manifest)
    if args.channel == "final" and not DOI_REGEX.match(str(manifest["doi"])):
        raise GateError("G11", "manifest has no valid DOI")
    write_json(work / "manifest.json", manifest)
    summary = {"tag": tag, "channel": args.channel, "tippecanoe": version_line,
               "pmtiles": {s["output"]: (work / s["output"]).stat().st_size for s in plan["tile_builds"]}}
    write_json(work / "finalize_summary.json", summary)

    if args.no_upload:
        log.info("--no-upload: manifest composed in %s, public bucket untouched", work)
        return 0
    publish(manifest, work, args.channel)
    if args.channel == "dev":
        update_dev_pointer(manifest)
    removed = staging.delete_prefix(prefix)
    log.info("staging cleaned: %d objects", removed)
    if args.channel == "final" and args.git_out:
        dst = Path(args.git_out) / args.dataset / f"v{args.version}"
        dst.mkdir(parents=True, exist_ok=True)
        for lp in manifest["layers"]:
            shutil.copyfile(work / lp["meta"]["path"], dst / lp["meta"]["path"])
            if "csv" in lp["files"]:
                shutil.copyfile(work / lp["files"]["csv"]["path"], dst / lp["files"]["csv"]["path"])
        for e in manifest.get("extra_files", []):
            if e["path"].endswith(".csv"):
                shutil.copyfile(work / e["path"], dst / e["path"])
        shutil.copyfile(work / "manifest.json", dst / "manifest.json")
        log.info("copied CSV, meta and manifest to %s", dst)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiles, manifest and publication of a staged release.")
    parser.add_argument("--dataset", required=True, choices=["abf-layers", "abf-boundaries"])
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", required=True, choices=["dev", "final"])
    parser.add_argument("--work", default="work", help="working folder")
    parser.add_argument("--tippecanoe", default="tippecanoe", help="path to the tippecanoe binary")
    parser.add_argument("--git-out", help="folder for the files that go to git (channel final)")
    parser.add_argument("--no-upload", action="store_true", help="stop after the manifest is composed")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        return run(args)
    except (GateError, StoreError) as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
