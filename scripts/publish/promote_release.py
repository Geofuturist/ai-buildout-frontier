"""Switch manifest/latest.json to the given versions of the datasets (runs in GitHub Actions).

Run command (normally by the workflow "Promote release"):
    python scripts/publish/promote_release.py --datasets abf-layers=0.1.0,abf-boundaries=0.1.0,abf-fra=0.1.0

The old form still works: --layers 0.1.0 --boundaries 0.1.0 (the same as
--datasets abf-layers=0.1.0,abf-boundaries=0.1.0).

Checks (any dataset name abf-<name> is accepted, abf-boundaries is required):
  * every manifest.json exists in the public bucket and carries a DOI;
  * the boundary_release of every other dataset is not newer than the boundaries in the list;
  * every unit_id in the CSV files of those datasets exists in the boundaries in the list.
Then it writes manifest/latest.json (abf-latest-1.0). The Vercel deploy hook is called by the workflow step.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DOI_REGEX, SCHEMA_DIR, GateError, read_json, setup_logging, sha256_file, utc_iso, write_json
from r2io import StoreError, open_store

log = logging.getLogger("publish.promote")

DATASET_RE = re.compile(r"abf-[a-z0-9]+")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
BOUNDARIES = "abf-boundaries"


def parse_datasets(text: str) -> dict[str, str]:
    """'abf-layers=0.1.0,abf-boundaries=0.1.0' -> {'abf-layers': '0.1.0', ...}."""
    result: dict[str, str] = {}
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        if "=" not in part:
            raise GateError("promote", f"'{part}' must look like abf-layers=0.1.0")
        name, version = (x.strip() for x in part.split("=", 1))
        if not DATASET_RE.fullmatch(name):
            raise GateError("promote", f"bad dataset name '{name}': it must look like abf-layers")
        if not VERSION_RE.fullmatch(version):
            raise GateError("promote", f"bad version '{version}' of {name}: it must look like 0.1.0")
        if name in result:
            raise GateError("promote", f"{name} is listed twice")
        result[name] = version
    if BOUNDARIES not in result:
        raise GateError("promote", f"{BOUNDARIES}=<version> must be in the list")
    return result


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def boundary_unit_ids(store: Any, manifest: dict[str, Any]) -> set[str]:
    """All unit_id of the boundaries release: column unit_id of its GeoParquet files."""
    import pyarrow.parquet as pq

    ids: set[str] = set()
    for layer in manifest["layers"]:
        ref = layer["files"].get("parquet")
        if ref is None:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "b.parquet"
            store.get_file(manifest["base_path"] + ref["path"], dest)
            if "unit_id" not in pq.read_schema(dest).names:
                continue
            ids.update(str(v) for v in pq.read_table(dest, columns=["unit_id"]).column("unit_id").to_pylist())
    if not ids:
        raise GateError("promote", "no unit_id found in the boundaries release")
    return ids


def layer_unit_ids(store: Any, manifest: dict[str, Any], layer: dict[str, Any]) -> set[str]:
    """unit_id values of the CSV of a layer (empty set if the layer has no such column)."""
    ref = layer["files"].get("csv")
    if ref is None:
        return set()
    raw = store.get_bytes(manifest["base_path"] + ref["path"])
    if raw is None:
        raise GateError("promote", f"{manifest['base_path']}{ref['path']} does not exist in the public bucket")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if "unit_id" not in (reader.fieldnames or []):
        return set()
    return {row["unit_id"].strip() for row in reader if row["unit_id"].strip()}


def promote(versions: dict[str, str]) -> int:
    import jsonschema

    store = open_store("R2_BUCKET")
    datasets: dict[str, dict[str, str]] = {}
    manifests: dict[str, dict[str, Any]] = {}
    for dataset, version in sorted(versions.items()):
        key = f"{dataset}/v{version}/manifest.json"
        raw = store.get_bytes(key)
        if raw is None:
            raise GateError("promote", f"{key} does not exist in the public bucket: the release is not finished")
        manifest = json.loads(raw)
        if not manifest.get("doi") or not DOI_REGEX.match(str(manifest["doi"])):
            raise GateError("G11", f"{key} has no valid DOI (doi = {manifest.get('doi')!r})")
        datasets[dataset] = {"version": version, "manifest": key}
        manifests[dataset] = manifest
        log.info("%s v%s: manifest found, doi %s", dataset, version, manifest["doi"])

    # boundary_release of every other dataset: not newer than the boundaries of the list,
    # and every unit_id of its files exists in those boundaries
    current = version_tuple(versions[BOUNDARIES])
    others = [d for d in sorted(versions) if d != BOUNDARIES]
    known_ids: set[str] | None = None
    for dataset in others:
        manifest = manifests[dataset]
        ref = manifest.get("boundary_release")
        if ref is None:
            continue
        m = re.fullmatch(rf"{BOUNDARIES}-v(\d+\.\d+\.\d+)", str(ref))
        if not m:
            raise GateError("promote", f"{dataset} has boundary_release {ref!r}, expected {BOUNDARIES}-v<version>")
        if version_tuple(m.group(1)) > current:
            raise GateError("promote", f"{dataset} refers to boundary_release {ref}, which is newer than "
                                       f"{BOUNDARIES}-v{versions[BOUNDARIES]} in the list")
        if known_ids is None:
            known_ids = boundary_unit_ids(store, manifests[BOUNDARIES])
            log.info("boundaries v%s: %d unit_id", versions[BOUNDARIES], len(known_ids))
        for layer in manifest["layers"]:
            used = layer_unit_ids(store, manifest, layer)
            unknown = sorted(used - known_ids)
            if unknown:
                raise GateError("promote", f"{dataset} / {layer['layer_id']}: {len(unknown)} unit_id are not in "
                                           f"{BOUNDARIES} v{versions[BOUNDARIES]}: {unknown[:5]}")
            log.info("%s / %s: %d unit_id, all in the boundaries", dataset, layer["layer_id"], len(used))

    doc = {"schema_version": "abf-latest-1.0", "updated_at": utc_iso(datetime.now(timezone.utc).replace(microsecond=0)),
           "datasets": datasets}
    jsonschema.validate(doc, read_json(SCHEMA_DIR / "latest.schema.json"), cls=jsonschema.Draft202012Validator)
    tmp = Path("latest.json.tmp")
    write_json(tmp, doc)
    store.put_file(tmp, "manifest/latest.json", sha256_file(tmp))
    tmp.unlink()
    log.info("manifest/latest.json now points to %s", {k: v["version"] for k, v in datasets.items()})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Point manifest/latest.json at the given versions.")
    parser.add_argument("--datasets", help="list dataset=version, e.g. abf-layers=0.1.0,abf-boundaries=0.1.0,abf-fra=0.1.0")
    parser.add_argument("--layers", help="old form: version of abf-layers, e.g. 0.1.0")
    parser.add_argument("--boundaries", help="old form: version of abf-boundaries, e.g. 0.1.0")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        if args.datasets:
            if args.layers or args.boundaries:
                raise GateError("promote", "use either --datasets or --layers/--boundaries, not both")
            versions = parse_datasets(args.datasets)
        elif args.layers and args.boundaries:
            versions = parse_datasets(f"abf-layers={args.layers},abf-boundaries={args.boundaries}")
        else:
            raise GateError("promote", "give --datasets, or both --layers and --boundaries")
        return promote(versions)
    except (GateError, StoreError) as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
