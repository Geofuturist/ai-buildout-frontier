"""Territory index files into a release folder (SPEC_INDEX_territory r8 section 7). Used by build_release.py.

The index itself is made by the data step of [CODE-GEM] (scripts/index/build_index.py) into a folder, by default
C:\\Users\\PGS\\Documents\\AI\\index_work\\data\\index\\, which holds per set (abf-dc, abf-energy, abf-energync):
    <ISO3>.csv, <ISO3>.csv.gz, adm0_other.csv, adm0_other.csv.gz, summary.csv, meta.json, index_<set>.zip
and, for all sets, build_hashes.json. This module checks those files and lays them out in the release folder:
    index/<set>/<ISO3>.csv.gz   adm0_other.csv.gz   summary.csv   meta.json   index_<set>.zip   listing.json
listing.json is made here: for every country file its path, bytes, sha256 of the .csv.gz (the file on R2), sha256_csv of the
CSV (the file in git, data/index/), rows. The release yaml says which sets go into the release:
    indexes_dir: 'C:\\Users\\PGS\\Documents\\AI\\index_work\\data\\index'
    indexes:
      - {set: abf-dc, of_dataset: abf-dc, of_version: "0.2.0"}
Every check that fails is a stop (G14).
"""
from __future__ import annotations

import gzip
import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from common import GateError, Report, read_json, resolve_path, sha256_file, write_json

log = logging.getLogger("publish.index")
ISO3 = re.compile(r"^[A-Z]{3}$")
META_SCHEMA = "abf-index-meta-1.0"
LISTING_SCHEMA = "abf-index-listing-1.0"


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _need(path: Path) -> Path:
    if not path.exists():
        raise GateError("G14", f"index file not found: {path} (is the folder of the index build the right one? indexes_dir)")
    return path


def build_one(item: dict[str, Any], src_root: Path, hashes: dict[str, str], out: Path, boundary_release: str,
              report: Report) -> dict[str, Any]:
    """Check one index set, copy its files into out/index/<set>/ and return the entry of build_plan.json."""
    s = item["set"]
    src = src_root / s
    if not src.is_dir():
        raise GateError("G14", f"index set folder not found: {src}")
    meta_path = _need(src / "meta.json")
    meta = read_json(meta_path)
    if meta.get("schema_version") != META_SCHEMA:
        raise GateError("G14", f"{s}: meta.json schema_version is {meta.get('schema_version')!r}, expected {META_SCHEMA}")
    if meta.get("set") != s:
        raise GateError("G14", f"{s}: meta.json belongs to the set {meta.get('set')!r}")
    if meta.get("boundary_release") != boundary_release:
        raise GateError("G14", f"{s}: the index is made on {meta.get('boundary_release')}, the release yaml has boundary_release {boundary_release}")
    countries = sorted(meta["files"])
    if not countries or any(not ISO3.match(c) for c in countries):
        raise GateError("G14", f"{s}: meta.json lists no country files or a code that is not ISO3")
    on_disk = sorted(p.name[:-7] for p in src.glob("*.csv.gz") if p.name != "adm0_other.csv.gz")
    if on_disk != countries:
        raise GateError("G14", f"{s}: country files on disk differ from meta.json: "
                               f"{sorted(set(on_disk) ^ set(countries))[:6]}")

    def expected(name: str) -> str:
        key = f"{s}/{name}"
        if key not in hashes:
            raise GateError("G14", f"{key} is not in build_hashes.json")
        return hashes[key]

    dst = out / "index" / s
    dst.mkdir(parents=True, exist_ok=True)
    rows_total = 0
    listing: list[dict[str, Any]] = []
    for iso in countries:
        gz_path, csv_path = _need(src / f"{iso}.csv.gz"), _need(src / f"{iso}.csv")
        gz_sha, csv_sha = sha256_file(gz_path), sha256_file(csv_path)
        info = meta["files"][iso]
        if gz_sha != expected(f"{iso}.csv.gz") or csv_sha != expected(f"{iso}.csv"):
            raise GateError("G14", f"{s}/{iso}: a file differs from build_hashes.json (the index was rebuilt after the hashes?)")
        if csv_sha != info["sha256"]:
            raise GateError("G14", f"{s}/{iso}: CSV SHA-256 differs from meta.json")
        body = gzip.decompress(gz_path.read_bytes())
        if body != csv_path.read_bytes():
            raise GateError("G14", f"{s}/{iso}: the .csv.gz does not unpack to the CSV")
        rows = max(body.count(b"\n") - 1, 0)
        if rows != info["rows"]:
            raise GateError("G14", f"{s}/{iso}: {rows} rows in the file, {info['rows']} in meta.json")
        if gz_path.stat().st_size != info["csv_gz_bytes"]:
            raise GateError("G14", f"{s}/{iso}: .csv.gz bytes differ from meta.json")
        rows_total += rows
        shutil.copyfile(gz_path, dst / gz_path.name)
        listing.append({"iso3": iso, "path": f"index/{s}/{iso}.csv.gz", "bytes": gz_path.stat().st_size,
                        "sha256": gz_sha, "sha256_csv": csv_sha, "rows": rows})
    if rows_total != meta["records"]:
        raise GateError("G14", f"{s}: {rows_total} rows in the country files, meta.json says {meta['records']} records")

    for name in ("adm0_other.csv.gz", "summary.csv", "meta.json", f"index_{s}.zip"):
        p = _need(src / name)
        if sha256_file(p) != expected(name):
            raise GateError("G14", f"{s}/{name} differs from build_hashes.json")
        shutil.copyfile(p, dst / name)
    # adm0_other.csv.gz must unpack to the plain CSV of the build
    other_csv = _need(src / "adm0_other.csv")
    if gzip.decompress((src / "adm0_other.csv.gz").read_bytes()) != other_csv.read_bytes():
        raise GateError("G14", f"{s}: adm0_other.csv.gz does not unpack to adm0_other.csv")
    with zipfile.ZipFile(src / f"index_{s}.zip") as z:
        names = z.namelist()
        bad = z.testzip()
    if bad or "meta.json" not in names or "summary.csv" not in names or sum(n.endswith(".csv.gz") for n in names) < len(countries):
        raise GateError("G14", f"{s}: index_{s}.zip is damaged or lacks meta.json, summary.csv or country files")

    write_json(dst / "listing.json", {"schema_version": LISTING_SCHEMA, "set": s, "files": listing})
    report.note(f"index {s}: {len(countries)} country files, {rows_total} rows, of {item['of_dataset']} {item['of_version']}")
    return {
        "index_id": f"index_{s}",
        "set": s,
        "of_dataset": item["of_dataset"],
        "of_version": str(item["of_version"]),
        "layer_ids": sorted(meta["layers"]),
        "meta": f"index/{s}/meta.json",
        "country_files": {"path_pattern": f"index/{s}/{{iso3}}.csv.gz", "count": len(countries), "listing": f"index/{s}/listing.json"},
        "adm0_other": f"index/{s}/adm0_other.csv.gz",
        "summary": f"index/{s}/summary.csv",
        "archive": f"index/{s}/index_{s}.zip",
        "listing_file": f"index/{s}/listing.json",
    }


def build_indexes(rel: dict[str, Any], out: Path, report: Report) -> list[dict[str, Any]]:
    """All indexes of a release yaml (key indexes). Returns the plan entries, [] if the release has none."""
    items = rel.get("indexes") or []
    if not items:
        return []
    if not rel.get("indexes_dir"):
        raise GateError("G14", "the release yaml has indexes but no indexes_dir")
    if not rel.get("boundary_release"):
        raise GateError("G14", "the release yaml has indexes but no boundary_release")
    src_root = resolve_path(rel["indexes_dir"])
    hashes = read_json(_need(src_root / "build_hashes.json"))["files"]
    entries = [build_one(item, src_root, hashes, out, str(rel["boundary_release"]), report) for item in items]
    sets = [e["set"] for e in entries]
    if len(set(sets)) != len(sets):
        raise GateError("G14", f"a set is listed twice in indexes: {sets}")
    return entries


def index_zenodo_names(entries: list[dict[str, Any]]) -> list[str]:
    """Files of the indexes for zenodo_files.txt: the archive of each index (it holds the country files, the summary and meta.json;
    the meta.json files of different sets have one name, so they are not listed alone)."""
    return [e["archive"] for e in entries]
