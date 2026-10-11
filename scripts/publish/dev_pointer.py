r"""Set manifest/dev.json to a given list of dataset versions (runs on the computer of V, needs the R2 keys).

Run command:
    python scripts\publish\dev_pointer.py abf-layers=0.1.0,abf-boundaries=0.1.0,abf-fra=0.1.0

For every dataset the manifest is looked up first under <dataset>/v<version>/ (a final release),
then under dev/<dataset>/v<version>/ (a dev build). The whole `datasets` part of manifest/dev.json
is replaced by the list, so a dataset that is not listed (for example a shelved one) disappears.
Add --dry-run to see the new file without writing it.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import SCHEMA_DIR, GateError, read_json, setup_logging, sha256_file, utc_iso, write_json
from promote_release import parse_datasets
from r2io import StoreError, open_store

log = logging.getLogger("publish.devpointer")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set manifest/dev.json to the given versions.")
    parser.add_argument("datasets", help="list dataset=version, abf-boundaries must be in it")
    parser.add_argument("--dry-run", action="store_true", help="show the new file, do not write it")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        import jsonschema

        versions = parse_datasets(args.datasets)
        store = open_store("R2_BUCKET")
        datasets = {}
        for name, version in sorted(versions.items()):
            for prefix in ("", "dev/"):
                key = f"{prefix}{name}/v{version}/manifest.json"
                if store.head(key) is not None:
                    datasets[name] = {"version": version, "manifest": key}
                    log.info("%s v%s: %s", name, version, key)
                    break
            else:
                raise GateError("dev_pointer", f"no manifest for {name} v{version}: neither "
                                               f"{name}/v{version}/ nor dev/{name}/v{version}/ exists in the public bucket")
        doc = {"schema_version": "abf-latest-1.0",
               "updated_at": utc_iso(datetime.now(timezone.utc).replace(microsecond=0)), "datasets": datasets}
        jsonschema.validate(doc, read_json(SCHEMA_DIR / "latest.schema.json"), cls=jsonschema.Draft202012Validator)
        print(json.dumps(doc, indent=2))
        if args.dry_run:
            print("--dry-run: manifest/dev.json NOT changed")
            return 0
        tmp = Path("dev.json.tmp")
        write_json(tmp, doc)
        store.put_file(tmp, "manifest/dev.json", sha256_file(tmp))
        tmp.unlink()
        log.info("manifest/dev.json written")
        return 0
    except (GateError, StoreError) as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
