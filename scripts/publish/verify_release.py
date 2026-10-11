r"""Independent check of a published release: download every file and compare with the manifest.

Run command (from the repository root, Windows):
    python scripts\publish\verify_release.py --url https://data.aibuildoutfrontier.org/abf-layers/v0.1.0/manifest.json --save-manifest "D:\GISData\release\abf-layers-v0.1.0"

Needs: python -m pip install jsonschema requests
Checks: size and SHA-256 of every file, the schema of manifest and of every meta.json,
the PMTiles header, a Range request, the cache header. With --save-manifest the manifest
is saved for the Zenodo upload. Nothing is written to R2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import SCHEMA_DIR, GateError, read_json, setup_logging

log = logging.getLogger("publish.verify")


def _session():  # noqa: ANN202
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=(500, 502, 503, 504))))
    s.mount("http://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5, status_forcelist=(500, 502, 503, 504))))
    return s


def files_of(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for layer in manifest["layers"]:
        for ref in [layer["meta"], *layer["files"].values(), *layer["extra_files"]]:
            out[ref["path"]] = ref
    for ref in [*manifest.get("extra_files", []), *manifest["source_archives"]]:
        out[ref["path"]] = ref
    return out


def verify(url: str, save_to: Path | None) -> int:
    import jsonschema

    sess = _session()
    r = sess.get(url, timeout=60)
    if r.status_code != 200:
        raise GateError("verify", f"manifest not reachable: HTTP {r.status_code} {url}")
    manifest = r.json()
    problems: list[str] = []
    # Stale-CDN check: the plain address (what a user gets) must equal a cache-busted copy.
    fresh = sess.get(url, params={"nocache": uuid.uuid4().hex}, timeout=60)
    if fresh.status_code != 200 or fresh.content != r.content:
        problems.append("manifest.json: the plain address gives a different (stale?) copy than the address with ?nocache=; "
                        f"cf-cache-status={r.headers.get('cf-cache-status')!r}, age={r.headers.get('age')!r}")
    jsonschema.validate(manifest, read_json(SCHEMA_DIR / "manifest.schema.json"), cls=jsonschema.Draft202012Validator)
    base_url = url[: url.rindex(manifest["base_path"] + "manifest.json")] if (manifest["base_path"] + "manifest.json") in url else None
    if base_url is None:
        raise GateError("verify", f"the url does not end with {manifest['base_path']}manifest.json")
    if manifest["doi"] is None:
        log.warning("manifest has doi = null (channel dev)")
    meta_schema = read_json(SCHEMA_DIR / "meta.schema.json")
    for rel, ref in sorted(files_of(manifest).items()):
        furl = base_url + manifest["base_path"] + rel
        digest, size = hashlib.sha256(), 0
        with sess.get(furl, stream=True, timeout=120) as resp:
            if resp.status_code != 200:
                problems.append(f"{rel}: HTTP {resp.status_code}")
                continue
            body = bytearray() if rel.endswith(".meta.json") else None
            for chunk in resp.iter_content(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                if body is not None:
                    body.extend(chunk)
            cache = resp.headers.get("cache-control", "")
            cf_status, age = resp.headers.get("cf-cache-status"), resp.headers.get("age")
        if size != ref["bytes"]:
            problems.append(f"{rel}: size {size} != manifest {ref['bytes']}")
        if digest.hexdigest() != ref["sha256"]:
            problems.append(f"{rel}: SHA-256 differs from the manifest")
        short_lived = (manifest["base_path"] + rel).startswith("dev/")
        if short_lived and cache.replace(" ", "") != "public,max-age=60":
            problems.append(f"{rel}: cache-control is {cache!r}, expected 'public, max-age=60' (dev channel)")
        if not short_lived and manifest["doi"] and "immutable" not in cache:
            problems.append(f"{rel}: cache-control is {cache!r}, expected immutable")
        if body is not None:
            # The same file with a cache-busting parameter must be byte-identical (no stale CDN copy).
            fr = sess.get(furl, params={"nocache": uuid.uuid4().hex}, timeout=60)
            if fr.status_code != 200 or fr.content != bytes(body):
                problems.append(f"{rel}: plain address differs from the ?nocache= copy (stale CDN copy); "
                                f"cf-cache-status={cf_status!r}, age={age!r}")
            try:
                jsonschema.validate(json.loads(body), meta_schema, cls=jsonschema.Draft202012Validator)
            except jsonschema.ValidationError as exc:
                problems.append(f"{rel}: meta.json does not match the schema: {exc.message[:150]}")
            meta = json.loads(body)
            if meta["release"]["doi"] != manifest["doi"]:
                problems.append(f"{rel}: DOI in meta ({meta['release']['doi']}) differs from the manifest ({manifest['doi']})")
        log.info("ok %s (%d bytes)", rel, size)
    for layer in manifest["layers"]:
        tile = layer["files"]["pmtiles"]
        furl = base_url + manifest["base_path"] + tile["path"]
        rr = sess.get(furl, headers={"Range": "bytes=0-16383"}, timeout=60)
        if rr.status_code != 206 or rr.content[:7] != b"PMTiles":
            problems.append(f"{tile['path']}: Range request gave HTTP {rr.status_code}, header {rr.content[:7]!r}")
    for key in ("manifest/dev.json", "manifest/latest.json"):
        mr = sess.get(base_url + key, timeout=60)
        if mr.status_code == 200:
            cc = mr.headers.get("cache-control", "").replace(" ", "")
            if cc != "public,max-age=60":
                problems.append(f"{key}: cache-control is {mr.headers.get('cache-control')!r}, expected 'public, max-age=60'")
            mf = sess.get(base_url + key, params={"nocache": uuid.uuid4().hex}, timeout=60)
            if mf.content != mr.content:
                problems.append(f"{key}: plain address differs from the ?nocache= copy (stale CDN copy)")
    if save_to:
        save_to.mkdir(parents=True, exist_ok=True)
        (save_to / "manifest.json").write_bytes(r.content)
        log.info("manifest saved to %s", save_to / "manifest.json")
    if problems:
        for p in problems:
            log.error("PROBLEM %s", p)
        print(f"\nНайдено проблем: {len(problems)}. Релиз не принимать.")
        return 1
    print(f"\nВсё сходится: {len(files_of(manifest))} файлов, размеры и SHA-256 как в манифесте.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a published release and compare it with its manifest.")
    parser.add_argument("--url", required=True, help="address of manifest.json")
    parser.add_argument("--save-manifest", help="folder to save a copy of manifest.json (for Zenodo)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        return verify(args.url, Path(args.save_manifest) if args.save_manifest else None)
    except GateError as exc:
        log.error("STOP %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
