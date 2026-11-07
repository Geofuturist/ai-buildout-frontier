"""Territory index files into a release folder (SPEC_INDEX_territory r8 section 7). Used by build_release.py.

The index itself is made by the data step of [CODE-GEM] (scripts/index/build_index.py) into a folder, by default
C:\\Users\\PGS\\Documents\\AI\\index_work\\data\\index\\, which holds per set (abf-dc, abf-energy, abf-energync):
    <ISO3>.csv, <ISO3>.csv.gz, adm0_other.csv, adm0_other.csv.gz, summary.csv, meta.json, index_<set>.zip
and, for all sets, build_hashes.json. This module checks those files and lays them out in the release folder:
    index/<set>/<ISO3>.csv.gz   adm0_other.csv.gz   summary.csv   meta.json   build_meta.json   index_<set>.zip   listing.json
    [rules/<name>.csv]
build_meta.json is the meta.json of the build of CODE-GEM, byte for byte (G14 stands on it). meta.json is the public file
made here (SPEC_INDEX r10 section 7): all keys of build_meta.json word for word plus the texts of the release yaml
(texts: [yaml, ...] of each index; sources and the descriptions of copied fields are copied from the published layer
meta.json files). The archive index_<set>.zip is built here, deterministically, from the country files, adm0_other.csv.gz,
summary.csv, the public meta.json and the rules files.
listing.json is made here: for every country file its path, bytes, sha256 of the .csv.gz (the file on R2), sha256_csv of the
CSV (the file in git, data/index/), rows. The release yaml says which sets go into the release:
    indexes_dir: 'C:\\Users\\PGS\\Documents\\AI\\index_work\\data\\index'
    indexes:
      - {set: abf-dc, of_dataset: abf-dc, of_version: "0.2.0"}
Every check that fails is a stop (G14).
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from common import GateError, Report, load_yaml, read_json, resolve_path, sha256_file, write_json

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


ZIP_TIME = (1980, 1, 1, 0, 0, 0)
TEXT_KEYS = ("title", "description", "attribution_text", "version_note", "release", "license", "sources", "fields", "null_meaning",
             "unit_note_descriptions", "known_gaps", "verification", "aggregations_labels", "totals_note")


def load_texts(item: dict[str, Any]) -> dict[str, Any]:
    """Merge the text yaml files of an index (item["texts"], in order; a later file overrides keys of an earlier one)."""
    paths = item.get("texts") or []
    if not paths:
        raise GateError("G14", f"{item['set']}: no texts in the release yaml (indexes[].texts)")
    out: dict[str, Any] = {}
    for p in paths:
        data = load_yaml(resolve_path(p))
        if not isinstance(data, dict):
            raise GateError("G14", f"{p}: not a mapping")
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = {**out[k], **v}
            else:
                out[k] = v
    return out


def copy_sources(layer_metas: dict[str, dict[str, Any]], layer_ids: list[str]) -> list[dict[str, Any]]:
    """sources[] of the index: the sources of the indexed layers (published meta.json), first occurrence of a source_id wins.
    The key `inputs` (hashes of the build files of the layer) is not copied: it describes the build of the layer, not the index."""
    seen: dict[str, dict[str, Any]] = {}
    for lid in layer_ids:
        for src in layer_metas[lid]["sources"]:
            if src["source_id"] not in seen:
                seen[src["source_id"]] = {k: v for k, v in src.items() if k != "inputs"}
    return list(seen.values())


def compose_fields(texts: dict[str, Any], layer_metas: dict[str, dict[str, Any]], header: list[str], s: str) -> list[dict[str, Any]]:
    """fields[] in the column order of the country CSV: texts of the project's own columns, copied descriptions of the rest."""
    own = texts.get("fields") or {}
    copied: dict[str, list[tuple[str, str]]] = {}
    for lid, names in (texts.get("copied_fields") or {}).items():
        by_name = {f["name"]: f for f in layer_metas[lid]["fields"]}
        for n in names:
            if n not in by_name:
                raise GateError("G14", f"{s}: copied field {n} is not a field of {lid} in its meta.json")
            copied.setdefault(n, []).append((lid, by_name[n]["description"]))
    out: list[dict[str, Any]] = []
    for col in header:
        if col in own and col in copied:
            raise GateError("G14", f"{s}: column {col} has a text of its own and a copied one")
        if col in own:
            out.append({"name": col, "description": str(own[col]).strip()})
        elif col in copied:
            parts = copied[col]
            desc = parts[0][1] if len(parts) == 1 else " ".join(f"{lid}: {d}" for lid, d in parts)
            out.append({"name": col, "description": desc, "copied_from": [lid for lid, _ in parts]})
        else:
            raise GateError("G14", f"{s}: column {col} of the index CSV has no text (fields / copied_fields of the texts)")
    unused = (set(own) | set(copied)) - set(header)
    if unused:
        raise GateError("G14", f"{s}: texts describe columns that the CSV does not have: {sorted(unused)}")
    return out


def compose_meta(item: dict[str, Any], build_meta: dict[str, Any], header: list[str], rel: dict[str, Any], doi: str | None,
                 built_at: str, published_at: str) -> dict[str, Any]:
    """The public meta.json of an index set (SPEC_INDEX r10 section 7)."""
    s = item["set"]
    texts = load_texts(item)
    layer_metas = {lid: read_json(resolve_path(p)) for lid, p in (item.get("layer_metas") or {}).items()}
    if set(layer_metas) != set(build_meta["layers"]):
        raise GateError("G14", f"{s}: layer_metas {sorted(layer_metas)} differ from the layers of the index {sorted(build_meta['layers'])}")
    for k in ("title", "description", "known_gaps", "verification", "null_meaning", "unit_note_descriptions"):
        if not texts.get(k):
            raise GateError("G14", f"{s}: the texts have no {k}")
    if set(texts["unit_note_descriptions"]) != set(build_meta["unit_note_values"]):
        raise GateError("G14", f"{s}: unit_note_descriptions {sorted(texts['unit_note_descriptions'])} differ from the unit_note_values "
                               f"of the build {sorted(build_meta['unit_note_values'])}")
    if not set(texts["null_meaning"]) <= set(header):
        raise GateError("G14", f"{s}: null_meaning names fields that are not columns: {sorted(set(texts['null_meaning']) - set(header))}")
    clash = [k for k in TEXT_KEYS if k in build_meta]
    if clash:
        raise GateError("G14", f"{s}: build_meta.json has keys that the texts use: {clash}")
    release_texts = rel.get("release_texts") or {}
    meta: dict[str, Any] = {
        "title": str(texts["title"]).strip(),
        "description": str(texts["description"]).strip(),
    }
    if release_texts.get("description"):
        meta["dataset_description"] = str(release_texts["description"]).strip()
    for k in ("attribution_text",):
        v = release_texts.get(k) or texts.get(k)
        if v:
            meta[k] = str(v).strip()
    if release_texts.get("version_note"):
        meta["version_note"] = str(release_texts["version_note"]).strip()
    meta["release"] = {"dataset": rel["dataset"], "version": str(rel["version"]), "tag": rel["tag"], "doi": doi,
                       "published_at": published_at, "built_at": built_at}
    meta["license"] = rel["license"]
    meta["sources"] = copy_sources(layer_metas, sorted(build_meta["layers"]))
    meta["fields"] = compose_fields(texts, layer_metas, header, s)
    meta["null_meaning"] = {k: str(v).strip() for k, v in texts["null_meaning"].items()}
    meta["unit_note_descriptions"] = {k: str(v).strip() for k, v in texts["unit_note_descriptions"].items()}
    meta["known_gaps"] = [str(x).strip() for x in texts["known_gaps"]]
    meta["verification"] = {k: str(v).strip() for k, v in texts["verification"].items()}
    if texts.get("aggregations_labels"):
        meta["aggregations_labels"] = {k: str(v).strip() for k, v in texts["aggregations_labels"].items()}
    if texts.get("totals_note"):
        meta["totals_note"] = str(texts["totals_note"]).strip()
    for k, v in build_meta.items():          # the technical keys of the build, word for word
        meta[k] = v
    return meta


def build_zip(path: Path, members: dict[str, bytes]) -> None:
    """Deterministic archive: names sorted, stored, fixed time and attributes."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for name in sorted(members):
            zi = zipfile.ZipInfo(name, ZIP_TIME)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, members[name])


def build_one(item: dict[str, Any], src_root: Path, hashes: dict[str, str], inputs: dict[str, Any], out: Path, boundary_release: str,
              report: Report, rel: dict[str, Any], doi: str | None, built_at: str, published_at: str) -> dict[str, Any]:
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
    header: list[str] | None = None
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
        head = next(csv.reader(io.StringIO(body.split(b"\n", 1)[0].decode("utf-8"))))
        if header is None:
            header = head
        elif head != header:
            raise GateError("G14", f"{s}/{iso}: the columns differ from the other country files")
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
    for name in ("adm0_other.csv.gz", "summary.csv"):
        shutil.copyfile(src / name, dst / name)
    shutil.copyfile(src / "meta.json", dst / "build_meta.json")      # the file of CODE-GEM, byte for byte
    # adm0_other.csv.gz must unpack to the plain CSV of the build
    other_csv = _need(src / "adm0_other.csv")
    if gzip.decompress((src / "adm0_other.csv.gz").read_bytes()) != other_csv.read_bytes():
        raise GateError("G14", f"{s}: adm0_other.csv.gz does not unpack to adm0_other.csv")
    # the archive of CODE-GEM is only checked (it holds the build meta.json); the published archive is built below
    with zipfile.ZipFile(src / f"index_{s}.zip") as z:
        names = z.namelist()
        bad = z.testzip()
    if bad or "meta.json" not in names or "summary.csv" not in names or sum(n.endswith(".csv.gz") for n in names) < len(countries):
        raise GateError("G14", f"{s}: index_{s}.zip is damaged or lacks meta.json, summary.csv or country files")

    # rules files (tables of the build that the index rests on), checked against the inputs of build_hashes.json
    rules_paths: list[str] = []
    members: dict[str, bytes] = {}
    for rname in item.get("rules") or []:
        rp = _need(src_root / rname)
        digests = inputs.get(rp.name) or {}
        if sha256_file(rp) not in (digests.get("sha256"), digests.get("sha256_lf")):
            raise GateError("G14", f"{s}: {rname} differs from the input of the build (build_hashes.json, inputs)")
        (dst / rname).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rp, dst / rname)
        rules_paths.append(f"index/{s}/{rname}")
        members[rname] = rp.read_bytes()

    meta_pub = compose_meta(item, meta, header or [], rel, doi, built_at, published_at)
    write_json(dst / "meta.json", meta_pub)
    for iso in countries:
        members[f"{iso}.csv.gz"] = (dst / f"{iso}.csv.gz").read_bytes()
    for name in ("adm0_other.csv.gz", "summary.csv", "meta.json"):
        members[name] = (dst / name).read_bytes()
    build_zip(dst / f"index_{s}.zip", members)

    write_json(dst / "listing.json", {"schema_version": LISTING_SCHEMA, "set": s, "files": listing})
    report.note(f"index {s}: {len(countries)} country files, {rows_total} rows, of {item['of_dataset']} {item['of_version']}")
    return {
        "index_id": f"index_{s}",
        "set": s,
        "of_dataset": item["of_dataset"],
        "of_version": str(item["of_version"]),
        "layer_ids": sorted(meta["layers"]),
        "meta": f"index/{s}/meta.json",
        "build_meta": f"index/{s}/build_meta.json",
        "rules": rules_paths,
        "country_files": {"path_pattern": f"index/{s}/{{iso3}}.csv.gz", "count": len(countries), "listing": f"index/{s}/listing.json"},
        "adm0_other": f"index/{s}/adm0_other.csv.gz",
        "summary": f"index/{s}/summary.csv",
        "archive": f"index/{s}/index_{s}.zip",
        "listing_file": f"index/{s}/listing.json",
    }


def build_indexes(rel: dict[str, Any], out: Path, report: Report, doi: str | None = None, built_at: str = "",
                  published_at: str = "") -> list[dict[str, Any]]:
    """All indexes of a release yaml (key indexes). Returns the plan entries, [] if the release has none."""
    items = rel.get("indexes") or []
    if not items:
        return []
    if not rel.get("indexes_dir"):
        raise GateError("G14", "the release yaml has indexes but no indexes_dir")
    if not rel.get("boundary_release"):
        raise GateError("G14", "the release yaml has indexes but no boundary_release")
    src_root = resolve_path(rel["indexes_dir"])
    bh = read_json(_need(src_root / "build_hashes.json"))
    if not rel.get("license"):
        raise GateError("G14", "the release yaml has indexes but no license block")
    entries = [build_one(item, src_root, bh["files"], bh.get("inputs") or {}, out, str(rel["boundary_release"]), report, rel, doi,
                         built_at, published_at) for item in items]
    sets = [e["set"] for e in entries]
    if len(set(sets)) != len(sets):
        raise GateError("G14", f"a set is listed twice in indexes: {sets}")
    return entries


def index_zenodo_names(entries: list[dict[str, Any]]) -> list[str]:
    """Files of the indexes for zenodo_files.txt: the archive of each index (it holds the country files, the summary and meta.json;
    the meta.json files of different sets have one name, so they are not listed alone)."""
    return [e["archive"] for e in entries]
