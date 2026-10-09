#!/usr/bin/env python3
"""
fetch_boundary_sources.py -- stage and verify the inputs for abf-boundaries-v0.1.0.

Run:
    python -m pip install "geopandas>=1.0" "shapely>=2.0" pyogrio pyarrow pyproj requests
    python scripts\\boundaries\\fetch_boundary_sources.py --sources-dir "D:\\GISData\\Boundaries\\sources"

What it does (SPEC_BND_boundaries_v0_1.md S1):
  - Downloads Natural Earth 5.1.2 (ADM0 _usa, ADM1, ADM2 counties, lakes) and the
    geoBoundaries metadata CSV straight from GitHub -- cached: a second run does not
    re-download a file that is already present with non-zero size.
  - Census (state/county cb_2023_500k) and Kartverket (Inndelingsbase fylker/kommuner)
    cannot be fetched automatically from this environment (census.gov is not reachable
    from a cloud session, and Kartverket's Inndelingsbase has no stable direct-download
    URL -- see PREFLIGHT_BND_v0_1.md S7.3/S7.6/S11). The script checks whether these
    files are already sitting in --sources-dir; if not, it prints exactly which file is
    missing and how to obtain it, and exits with a non-zero code without starting the
    build.
  - Extracts every .zip source into sources-dir/extracted/<key>/ (idempotent).
  - Writes sources_manifest.json: url (or "manual"), retrieved_at, size, sha256,
    license, publisher/product, for every source file.

Exit code is non-zero if any required source is missing after the attempt above.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnd_common as c  # noqa: E402

try:
    import requests
except ImportError:
    print(
        "requests is not installed. Run:\n"
        "  python -m pip install requests\n"
        "(see also: python -m pip install \"geopandas>=1.0\" \"shapely>=2.0\" pyogrio pyarrow pyproj requests)",
        file=sys.stderr,
    )
    sys.exit(2)


# Each entry: key, filename (as it will sit in --sources-dir), url (None = manual only),
# publisher, product, license, required (False = best-effort, does not fail the run),
# manual_instructions (shown only if the file is missing and could not be downloaded).
SOURCES = [
    dict(
        key="ne_adm0_usa",
        filename="ne_10m_admin_0_countries_usa.geojson",
        url=c.NE_BASE_URL + "ne_10m_admin_0_countries_usa.geojson",
        publisher="Natural Earth", product=f"ne_10m_admin_0_countries_usa {c.NE_VERSION}",
        license="public domain", required=True,
    ),
    dict(
        key="ne_adm1",
        filename="ne_10m_admin_1_states_provinces.geojson",
        url=c.NE_BASE_URL + "ne_10m_admin_1_states_provinces.geojson",
        publisher="Natural Earth", product=f"ne_10m_admin_1_states_provinces {c.NE_VERSION}",
        license="public domain", required=True,
    ),
    dict(
        key="ne_adm2_counties",
        filename="ne_10m_admin_2_counties.geojson",
        url=c.NE_BASE_URL + "ne_10m_admin_2_counties.geojson",
        publisher="Natural Earth", product=f"ne_10m_admin_2_counties {c.NE_VERSION}",
        license="public domain", required=True,  # only used by validation check 6, but SPEC S1 lists it as required input
    ),
    dict(
        key="ne_lakes",
        filename="ne_10m_lakes.geojson",
        url=c.NE_BASE_URL + "ne_10m_lakes.geojson",
        publisher="Natural Earth", product=f"ne_10m_lakes {c.NE_VERSION}",
        license="public domain", required=True,
    ),
    dict(
        key="census_state",
        filename="cb_2023_us_state_500k.zip",
        url="https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip",
        publisher="US Census Bureau", product="cb_2023_us_state_500k",
        license="U.S. Government Work", required=True,
        manual_instructions=(
            "Download it yourself from\n"
            "    https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip\n"
            "  and place it at the path above."
        ),
    ),
    dict(
        key="census_county",
        filename="cb_2023_us_county_500k.zip",
        url="https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip",
        publisher="US Census Bureau", product="cb_2023_us_county_500k",
        license="U.S. Government Work", required=True,
        manual_instructions=(
            "Download it yourself from\n"
            "    https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip\n"
            "  or copy your existing copy of this exact file to the path above (you already\n"
            "  had one on disk during pre-flight -- SPEC S1)."
        ),
    ),
    dict(
        key="kartverket_fylker",
        filename="Basisdata_0000_Norge_3135_Fylker_GeoJSON.geojson",
        url=None,
        publisher="Kartverket", product="Administrative enheter fylker (Inndelingsbase)",
        license="CC BY 4.0", required=True,
        manual_instructions=(
            "No stable direct-download URL (Kartkatalog is a JS single-page app; the\n"
            "  card originally named in SPEC S1 no longer resolves -- see\n"
            "  CODE_to_ARCH_BND_norway_source_change_v0_1.md). Get it from\n"
            "    https://data.norge.no/nb/datasets/cffde12f-3530-4406-9aa0-d6d4519ef077/administrative-enheter-fylker\n"
            "  (GeoJSON distribution) and place it at the path above with this exact name."
        ),
    ),
    dict(
        key="kartverket_kommuner",
        filename="Basisdata_0000_Norge_25833_Kommuner_GeoJSON.zip",
        url=None,
        publisher="Kartverket", product="Administrative enheter kommuner (Inndelingsbase)",
        license="CC BY 4.0", required=True,
        manual_instructions=(
            "No stable direct-download URL -- same product family as the fylker file above.\n"
            "  Get it from\n"
            "    https://data.norge.no/en/datasets/3557d23d-8188-4136-b227-c854f89a6e8e/administrative-enheter-kommuner\n"
            "  and place it at the path above with this exact name."
        ),
    ),
    dict(
        key="geoboundaries_meta",
        filename="geoBoundariesOpen-meta.csv",
        url=c.GEOBOUNDARIES_META_URL,
        publisher="geoBoundaries", product="geoBoundariesOpen-meta",
        license="mixed by country (not used for geometry)", required=False,
    ),
]


def download(url: str, dest: Path, timeout: int = 60) -> None:
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.replace(dest)


def extract_if_zip(path: Path, sources_dir: Path, key: str) -> Path | None:
    if path.suffix.lower() != ".zip":
        return None
    out_dir = sources_dir / "extracted" / key
    if out_dir.exists() and any(out_dir.iterdir()):
        return out_dir  # already extracted -- idempotent
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(out_dir)
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources-dir", required=True, type=Path)
    args = ap.parse_args()

    sources_dir: Path = args.sources_dir
    sources_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    missing_required: list[str] = []

    for src in SOURCES:
        dest = sources_dir / src["filename"]
        got_it = dest.exists() and dest.stat().st_size > 0

        if not got_it and src["url"] is not None:
            print(f"[fetch] {src['key']}: downloading {src['url']}")
            try:
                download(src["url"], dest)
                got_it = True
            except Exception as e:  # noqa: BLE001 -- deliberately broad: any network failure falls back to manual
                print(f"[fetch] {src['key']}: download failed ({type(e).__name__}: {e}).")
        elif got_it:
            print(f"[fetch] {src['key']}: already present at {dest} -- skipping download (cache).")

        if not got_it:
            if src["url"] is None:
                print(f"[fetch] {src['key']}: no automatic source. {src.get('manual_instructions', '')}")
            else:
                print(f"[fetch] {src['key']}: not available. {src.get('manual_instructions', 'Place the file manually at ' + str(dest))}")
            if src["required"]:
                missing_required.append(src["filename"])
                continue
            else:
                print(f"[fetch] {src['key']}: optional, continuing without it.")
                continue

        extracted_dir = extract_if_zip(dest, sources_dir, src["key"])

        manifest[src["key"]] = {
            "filename": src["filename"],
            # Resolved (absolute) paths -- the manifest must stay valid no matter what
            # working directory a later script (build_boundaries.py) is run from.
            "path": str(dest.resolve()),
            "extracted_to": str(extracted_dir.resolve()) if extracted_dir else None,
            "url": src["url"] or "manual (see README / SPEC S1)",
            "publisher": src["publisher"],
            "product": src["product"],
            "license": src["license"],
            "retrieved_at": c.now_iso(),
            "size_bytes": dest.stat().st_size,
            "sha256": c.sha256_file(dest),
        }
        print(f"[fetch] {src['key']}: OK, sha256={manifest[src['key']]['sha256'][:12]}...")

    manifest_path = sources_dir / "sources_manifest.json"
    import json

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch] wrote {manifest_path}")

    if missing_required:
        print("\n[fetch] BUILD BLOCKED -- required source files are missing:")
        for f in missing_required:
            print(f"  - {f}")
        print("Place the files above in the sources directory and re-run this script.")
        return 1

    print("\n[fetch] all required sources present. You can run build_boundaries.py now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
