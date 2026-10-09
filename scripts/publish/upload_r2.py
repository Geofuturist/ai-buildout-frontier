"""Upload a built release to the private staging bucket, or check access to R2.

Run commands (from the repository root, Windows):
    python scripts\\publish\\upload_r2.py --check
    python scripts\\publish\\upload_r2.py --release-dir "D:\\GISData\\release\\abf-layers-v0.1.0" --stage

Needs: python -m pip install boto3
Keys are read from the environment variables R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_STAGING_BUCKET (SPEC_META section 8).
This script writes only to the staging bucket, never to the public one.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import GateError, read_json, setup_logging, sha256_file
from r2io import StoreError, open_store

log = logging.getLogger("publish.upload")

NOT_UPLOADED = {"release_report.md", "build_log.json", "zenodo_files.txt", "manifest.json"}


def check_access() -> int:
    """List both buckets; write and delete one test object in staging."""
    staging = open_store("R2_STAGING_BUCKET")
    public = open_store("R2_BUCKET")
    n_pub = sum(1 for _ in public.list(""))
    log.info("public bucket %s: readable, %d objects", public.bucket, n_pub)
    key = f"_access_check/{int(time.time())}.txt"
    staging.put_bytes(b"abf access check\n", key)
    got = staging.get_bytes(key)
    staging.delete_prefix("_access_check/")
    if got != b"abf access check\n":
        raise StoreError("staging bucket: written object could not be read back")
    log.info("staging bucket %s: write, read and delete work", staging.bucket)
    return 0


def stage(release_dir: Path) -> int:
    plan_path = release_dir / "build_plan.json"
    if not plan_path.exists():
        raise GateError("stage", f"{plan_path} not found: run build_release.py first")
    plan = read_json(plan_path)
    prefix = f"{plan['channel']}/{plan['tag']}/"
    store = open_store("R2_STAGING_BUCKET")
    files = [p for p in sorted(release_dir.rglob("*")) if p.is_file()
             and p.relative_to(release_dir).as_posix() not in NOT_UPLOADED]
    wanted = {prefix + p.relative_to(release_dir).as_posix() for p in files}
    stale = [i["key"] for i in store.list(prefix) if i["key"] not in wanted]
    for key in stale:
        log.info("removing stale staging object %s", key)
    if stale:
        # delete only the stale keys, one prefix call per key is fine for a handful of files
        for key in stale:
            store.delete_prefix(key)
    sent = skipped = 0
    total = 0
    for p in files:
        key = prefix + p.relative_to(release_dir).as_posix()
        digest = sha256_file(p)
        head = store.head(key)
        total += p.stat().st_size
        if head and head["bytes"] == p.stat().st_size and head.get("sha256") == digest:
            skipped += 1
            continue
        log.info("upload %s (%.1f MB)", key, p.stat().st_size / 1e6)
        store.put_file(p, key, digest)
        sent += 1
    log.info("staging done: %d sent, %d already there, %.1f MB in total, prefix %s", sent, skipped, total / 1e6, prefix)
    print(f"\nГотово: {sent} файлов загружено, {skipped} уже были. Дальше: GitHub -> Actions -> «Build tiles and finalize» "
          f"(dataset={plan['dataset']}, version={plan['version']}, channel={plan['channel']}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a release to the staging bucket or check R2 access.")
    parser.add_argument("--release-dir", help="folder made by build_release.py")
    parser.add_argument("--stage", action="store_true", help="upload to the private staging bucket")
    parser.add_argument("--check", action="store_true", help="check access to both buckets")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        if args.check:
            return check_access()
        if args.stage and args.release_dir:
            return stage(Path(args.release_dir))
        parser.error("use --check, or --release-dir together with --stage")
    except (GateError, StoreError) as exc:
        log.error("STOP %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
