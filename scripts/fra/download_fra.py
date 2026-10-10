r"""Download what the script fetches for France (SPEC_FRA_layers_v0_1 r2, CHECKLIST appendix).

Run from the repo root::

    python scripts\fra\download_fra.py
    python scripts\fra\download_fra.py --skip-commune   # catalogue + licences only

What it does:
  1. Agence ORE (data-fair catalogue): looks for an annual consumption dataset by department
     first (SPEC_FRA §4, principle 3); writes the candidate list. Downloads the department
     dataset if one exists, otherwise the commune file (~840 MB, streamed);
  2. saves dataset pages as RAW HTML for the licence extracts (SPEC_FRA §2) into
     research\fra\licences\<source>.html - the extract itself is done by preflight_fra.py;
  3. obeys robots.txt: a disallowed URL is not fetched, it is listed for V instead;
  4. writes a manifest (url, file, bytes, sha256, UTC time) to research\fra\download_manifest.json.

Nothing here touches the layers; inputs go to D:\GISData\Energy\France\<source>\.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(r"D:\GISData\Energy\France")
REPO = Path.cwd()
RES = REPO / "research" / "fra"
LIC = RES / "licences"
UA = "ABF-observatory-preflight/0.1 (research; contact via project)"

ORE_API = "https://opendata.agenceore.fr/data-fair/api/v1/datasets"
ORE_COMMUNE_ID = "consommation-annuelle-d-electricite-et-gaz-par-commune"

# Raw HTML pages kept for the licence extracts (SPEC_FRA §2).
LICENCE_PAGES = {
    "odre_registre": "https://odre.opendatasoft.com/explore/dataset/"
                     "registre-national-installation-production-stockage-electricite-agrege/information/",
    "odre_rte_lignes_aeriennes": "https://odre.opendatasoft.com/explore/dataset/lignes-aeriennes-rte-nv/information/",
    "odre_rte_lignes_souterraines": "https://odre.opendatasoft.com/explore/dataset/lignes-souterraines-rte-nv/information/",
    "agenceore_consommation": "https://www.data.gouv.fr/api/1/datasets/"
                              "consommation-annuelle-delectricite-et-gaz-par-commune/",
    "georisques_icpe": "https://www.georisques.gouv.fr/donnees/bases-de-donnees/installations-industrielles",
    "datagouv_icpe": "https://www.data.gouv.fr/api/1/datasets/base-des-installations-classees-icpe/",
    "datagouv_rte_lignes_ddtm": "https://www.data.gouv.fr/api/1/datasets/lignes-aeriennes-rte/",
}

# F2 geometry: the portal's parquet export has no geometry column (pre-flight 10.10), so the
# GeoJSON export of the same datasets is fetched through the Explore API, if robots.txt allows.
ODS = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"
RTE_GEOJSON = {f"{d}.geojson": f"{ODS}/{d}/exports/geojson"
               for d in ("lignes-aeriennes-rte-nv", "lignes-souterraines-rte-nv")}
RTE_META = {f"{d}_meta.json": f"{ODS}/{d}" for d in ("lignes-aeriennes-rte-nv",
                                                      "lignes-souterraines-rte-nv")}
F1_META = {"registre_meta.json": f"{ODS}/registre-national-installation-production-stockage-electricite-agrege"}

manifest: list[dict] = []
blocked: list[str] = []
_robots: dict[str, urllib.robotparser.RobotFileParser] = {}


def allowed(url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:  # noqa: BLE001 - no robots.txt reachable: treat as allowed
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def fetch(url: str, dest: Path, stream: bool = False) -> bool:
    if not allowed(url):
        blocked.append(url)
        print(f"  robots.txt запрещает: {url} — пункт для V")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    n = 0
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                n += len(chunk)
                if stream and n % (100 << 20) < (1 << 20):
                    print(f"  … {n / 1e6:,.0f} МБ")
    except Exception as exc:  # noqa: BLE001 - report and go on
        print(f"  ошибка: {url}: {exc}")
        manifest.append({"url": url, "file": str(dest), "error": str(exc)})
        return False
    manifest.append({"url": url, "file": str(dest), "bytes": n, "sha256": h.hexdigest(),
                     "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    print(f"  ок: {dest.name} ({n / 1e6:,.1f} МБ)")
    return True


def ore_catalogue() -> list[dict]:
    """Search the Agence ORE catalogue for consumption datasets (department first)."""
    found: dict[str, dict] = {}
    for q in ("consommation departement", "consommation annuelle", "consommation electricite"):
        url = f"{ORE_API}?q={urllib.parse.quote(q)}&size=100"
        dest = RES / "agenceore_catalogue" / f"search_{q.replace(' ', '_')}.json"
        if not fetch(url, dest):
            continue
        for d in json.loads(dest.read_text(encoding="utf-8")).get("results", []):
            found[d.get("id")] = {
                "id": d.get("id"), "title": d.get("title"),
                "license": (d.get("license") or {}).get("title"),
                "license_href": (d.get("license") or {}).get("href"),
                "updated": d.get("dataUpdatedAt") or d.get("updatedAt"),
                "bytes": (d.get("file") or {}).get("size") or (d.get("originalFile") or {}).get("size"),
            }
    rows = sorted(found.values(), key=lambda r: r["id"] or "")
    (RES / "agenceore_catalogue" / "candidates.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return rows


def is_dept_dataset(r: dict) -> bool:
    t = f"{r.get('id', '')} {r.get('title', '')}".lower()
    return ("consommation" in t and ("departement" in t or "département" in t)
            and ("electricite" in t or "électricité" in t or "annuelle" in t))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-odre", action="store_true",
                    help="only the RTE GeoJSON, ODRÉ metadata and licence pages")
    ap.add_argument("--skip-commune", action="store_true",
                    help="do not download the ~840 MB commune file")
    args = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)

    if args.only_odre:
        args.skip_commune = True
    print("1. Agence ORE — каталог")
    cands = [] if args.only_odre else ore_catalogue()
    dept = [r for r in cands if is_dept_dataset(r)]
    for r in cands:
        print(f"  {'*' if r in dept else ' '} {r['id']} — {r['title']} ({r['updated']})")
    out = ROOT / "agenceore_consommation"
    for r in dept:  # department datasets first (SPEC_FRA §4)
        fetch(f"{ORE_API}/{r['id']}/raw", out / f"{r['id']}.csv", stream=True)
        fetch(f"{ORE_API}/{r['id']}", out / f"{r['id']}_meta.json")
    if not dept and not args.only_odre:
        print("  набора по департаментам нет — файл по коммунам")
    if not args.skip_commune:
        target = out / f"{ORE_COMMUNE_ID}.csv"
        if target.exists():
            print(f"  уже есть: {target.name} — не качаю повторно")
        else:
            fetch(f"{ORE_API}/{ORE_COMMUNE_ID}/raw", target, stream=True)
        fetch(f"{ORE_API}/{ORE_COMMUNE_ID}", out / f"{ORE_COMMUNE_ID}_meta.json")

    if True:
        print("1b. ODRÉ — геометрия линий RTE (GeoJSON) и метаданные наборов")
        for name, url in RTE_GEOJSON.items():
            fetch(url, ROOT / "odre_rte_lignes" / name, stream=True)
        for name, url in {**RTE_META}.items():
            fetch(url, ROOT / "odre_rte_lignes" / name)
        for name, url in F1_META.items():
            fetch(url, ROOT / "odre_registre" / name)

    print("2. Страницы лицензий — сырой HTML")
    for name, url in LICENCE_PAGES.items():
        ext = ".json" if "/api/" in url else ".html"
        fetch(url, LIC / f"{name}{ext}")

    (RES / "download_manifest.json").write_text(
        json.dumps({"files": manifest, "robots_blocked": blocked}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\nМанифест: {RES / 'download_manifest.json'}")
    if blocked:
        print("robots.txt закрыл адреса — их открыть вручную (V):")
        for u in blocked:
            print("  ", u)
    print("Дальше: python scripts\\fra\\preflight_fra.py")


if __name__ == "__main__":
    sys.exit(main())
