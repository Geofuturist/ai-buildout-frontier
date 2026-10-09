"""Switch manifest/latest.json to the given versions of both datasets (runs in GitHub Actions).

Run command (normally by the workflow "Promote release"):
    python scripts/publish/promote_release.py --layers 0.1.0 --boundaries 0.1.0

Checks that both manifest.json files exist and carry a DOI, then writes manifest/latest.json
(abf-latest-1.0). The Vercel deploy hook is called by the workflow step after this script.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DOI_REGEX, SCHEMA_DIR, GateError, read_json, setup_logging, sha256_file, utc_iso, write_json
from r2io import StoreError, open_store

log = logging.getLogger("publish.promote")


def promote(versions: dict[str, str]) -> int:
    import jsonschema

    store = open_store("R2_BUCKET")
    datasets = {}
    for dataset, version in sorted(versions.items()):
        key = f"{dataset}/v{version}/manifest.json"
        raw = store.get_bytes(key)
        if raw is None:
            raise GateError("promote", f"{key} does not exist in the public bucket: the release is not finished")
        manifest = json.loads(raw)
        if not manifest.get("doi") or not DOI_REGEX.match(str(manifest["doi"])):
            raise GateError("G11", f"{key} has no valid DOI (doi = {manifest.get('doi')!r})")
        datasets[dataset] = {"version": version, "manifest": key}
        log.info("%s v%s: manifest found, doi %s", dataset, version, manifest["doi"])
    layers = json.loads(store.get_bytes(datasets["abf-layers"]["manifest"]))
    want = f"abf-boundaries-v{versions['abf-boundaries']}"
    if layers.get("boundary_release") != want:
        raise GateError("promote", f"abf-layers refers to boundary_release {layers.get('boundary_release')!r}, not {want}")
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
    parser.add_argument("--layers", required=True, help="version of abf-layers, e.g. 0.1.0")
    parser.add_argument("--boundaries", required=True, help="version of abf-boundaries, e.g. 0.1.0")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        return promote({"abf-layers": args.layers, "abf-boundaries": args.boundaries})
    except (GateError, StoreError) as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
