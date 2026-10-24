r"""abf-dc: stage the downloadable inputs (SPEC_DC_world_v0_1_0 r2, section 9 Q5/Q6).

Run (Windows cmd, from the repo root)::

    python -m pip install pandas pyarrow shapely geopandas pyproj requests openpyxl
    python scripts\dc\dc_fetch.py --sources-dir "D:\GISData\DC\sources"

What it fetches (robots.txt of each host is read first; a disallowed path is not requested):
  * Census Gazetteer 2023, places (www2.census.gov)            -> census/2023_Gaz_place_national.txt
  * abf-boundaries v0.2.0 (Zenodo 10.5281/zenodo.23454136), only the files the build needs:
    units.csv, adm0.parquet, analysis_usa_adm2.parquet, contested_areas.parquet, contested_areas.csv
    paths /records/23454136/files/<name>; pause >= 10 s; md5 checked against the record's file list
    (/api/records/23454136/files, the one API path robots.txt allows).
A cached file is not downloaded again if its md5 (Zenodo) or sha256 (Census, from the first run) matches.

Writes <sources-dir>/sources_manifest_fetch.json (url, retrieved_at, size, sha256, md5, license) and
fetch_log.json (every request, including robots.txt and refusals).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc_http as H  # noqa: E402

ZENODO_RECORD = "23454136"
ZENODO_FILES = ["units.csv", "adm0.parquet", "analysis_usa_adm2.parquet", "contested_areas.parquet", "contested_areas.csv"]
CENSUS_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources-dir", required=True, type=Path)
    a = ap.parse_args()
    sd: Path = a.sources_dir
    sd.mkdir(parents=True, exist_ok=True)
    f = H.Fetcher(sd / "_cache")
    manifest_path = sd / "sources_manifest_fetch.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    # --- Zenodo: file list (allowed path), then the files ---
    lst = f.get(f"https://zenodo.org/api/records/{ZENODO_RECORD}/files", note="zenodo file list")
    if lst is None:
        print("STOP: could not read the Zenodo file list (see fetch_log.json).", file=sys.stderr)
        _write(sd, f, manifest)
        return 2
    entries = {e["key"]: e for e in lst.json()["entries"]}
    for name in ZENODO_FILES:
        e = entries.get(name)
        if e is None:
            print(f"STOP: {name} is not in the record's file list.", file=sys.stderr)
            return 2
        md5 = e["checksum"].split(":", 1)[1]
        dest = sd / "frame" / name
        if dest.exists() and H.file_hashes(dest)[1] == md5:
            print(f"[fetch] {name}: cached, md5 ok")
        else:
            r = f.get(f"https://zenodo.org/records/{ZENODO_RECORD}/files/{name}?download=1", dest, expect_md5=md5, note="abf-boundaries v0.2.0")
            if r is None:
                print(f"STOP: {name} was not downloaded (see fetch_log.json).", file=sys.stderr)
                _write(sd, f, manifest)
                return 2
            print(f"[fetch] {name}: ok")
        sha, md = H.file_hashes(dest)
        manifest[f"frame/{name}"] = dict(url=f"https://zenodo.org/records/{ZENODO_RECORD}/files/{name}", doi="10.5281/zenodo.23454136",
                                         retrieved_at=H.now_utc(), size=dest.stat().st_size, sha256=sha, md5=md,
                                         publisher="AI Buildout Frontier", product="abf-boundaries v0.2.0", license="see abf-boundaries v0.2.0 (CC BY 4.0)")

    # --- Census Gazetteer ---
    zpath = sd / "census" / "2023_Gaz_place_national.zip"
    prev = manifest.get("census/2023_Gaz_place_national.zip", {}).get("sha256")
    if not (zpath.exists() and prev and H.file_hashes(zpath)[0] == prev):
        r = f.get(CENSUS_URL, zpath, note="Census Gazetteer 2023 places")
        if r is None:
            print("STOP: Census Gazetteer was not downloaded (see fetch_log.json). Put the file at", zpath, file=sys.stderr)
            _write(sd, f, manifest)
            return 2
    sha, md = H.file_hashes(zpath)
    manifest["census/2023_Gaz_place_national.zip"] = dict(url=CENSUS_URL, retrieved_at=H.now_utc(), size=zpath.stat().st_size, sha256=sha, md5=md,
                                                          publisher="U.S. Census Bureau", product="2023 Gazetteer Files, Places", license="U.S. Government Work")
    with zipfile.ZipFile(zpath) as z:
        z.extract("2023_Gaz_place_national.txt", sd / "census")
    t = sd / "census" / "2023_Gaz_place_national.txt"
    s2, m2 = H.file_hashes(t)
    manifest["census/2023_Gaz_place_national.txt"] = dict(url=CENSUS_URL + "!2023_Gaz_place_national.txt", retrieved_at=manifest["census/2023_Gaz_place_national.zip"]["retrieved_at"],
                                                          size=t.stat().st_size, sha256=s2, md5=m2, publisher="U.S. Census Bureau",
                                                          product="2023 Gazetteer Files, Places", license="U.S. Government Work")
    _write(sd, f, manifest)
    print("OK. Next: scripts\\dc\\dc_build.py")
    return 0


def _write(sd: Path, f: H.Fetcher, manifest: dict) -> None:
    (sd / "sources_manifest_fetch.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    old = []
    lp = sd / "fetch_log.json"
    if lp.exists():
        old = json.loads(lp.read_text(encoding="utf-8"))
    (sd / "fetch_log.json").write_text(json.dumps(old + f.log, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
