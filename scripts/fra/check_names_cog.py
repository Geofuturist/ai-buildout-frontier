r"""France unit names against the INSEE Code officiel géographique (SPEC_META r8 §6 p.24, [ARCH] 11.10).

Run from the repo root:
    python scripts\fra\check_names_cog.py

1. Downloads the COG 2026 lists of regions and departments (INSEE, CSV) and the two pages that
   describe them into D:\GISData\Energy\France\insee_cog\ (skipped if the files are already there;
   robots.txt is obeyed).
2. Compares by code the 18 FRA-1-* and 101 FRA-2-* units of abf-boundaries-v0.1.0 with the COG.
   Names must match exactly (hyphens, apostrophes, diacritics); both sides are only put in
   Unicode NFC form and stripped of surrounding spaces.
3. Every mismatch -> boundaries\name_overrides.csv (rows of other countries are kept).
   Report -> research\fra\check_names_cog_<date>.md.
Stops if a unit has no COG code or the COG has a code that the boundaries do not.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import unicodedata
import urllib.request
import urllib.robotparser
from pathlib import Path

import pandas as pd

SCRIPT = "script:check_names_cog"
REPO = Path.cwd()
BND = Path(r"D:\GISData\Boundaries\out\abf-boundaries-v0.1.0\display")
DEST = Path(r"D:\GISData\Energy\France\insee_cog")
OVERRIDES = REPO / "boundaries" / "name_overrides.csv"
REPORT_DIR = REPO / "research" / "fra"
UA = "ABF-observatory/0.1 (research; contact via project)"
PAGE = "https://www.insee.fr/fr/information/8740222"
LICENCE_PAGE = "https://www.data.gouv.fr/datasets/code-officiel-geographique-cog"
FILES = {
    "region": "https://www.insee.fr/fr/statistiques/fichier/8740222/v_region_2026.csv",
    "departement": "https://www.insee.fr/fr/statistiques/fichier/8740222/v_departement_2026.csv",
}
COLS = ["unit_id", "name_source", "name", "source", "checked_at", "checked_by"]


def allowed(url: str) -> bool:
    base = "/".join(url.split("/")[:3])
    rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
    try:
        rp.read()
    except Exception:  # noqa: BLE001 - no robots.txt reachable: treat as allowed
        return True
    return rp.can_fetch(UA, url)


def fetch(url: str, dest: Path) -> dict:
    if not dest.exists():
        if not allowed(url):
            sys.exit(f"СТОП: robots.txt запрещает {url}. Скачайте вручную в {dest}")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
    data = dest.read_bytes()
    return {"url": url, "file": dest.name, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def nfc(s) -> str:
    return unicodedata.normalize("NFC", str(s)).strip()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = [fetch(PAGE, DEST / "cog_2026_page.html"),
                fetch(LICENCE_PAGE, DEST / "cog_datagouv_page.html")]
    cog = {}
    for kind, url in FILES.items():
        manifest.append(fetch(url, DEST / url.rsplit("/", 1)[1]))
        t = pd.read_csv(DEST / url.rsplit("/", 1)[1], dtype=str, encoding="utf-8")
        code = "REG" if kind == "region" else "DEP"
        level = 1 if kind == "region" else 2
        cog.update({f"FRA-{level}-{c}": nfc(n) for c, n in zip(t[code], t["LIBELLE"])})
    (DEST / "download_manifest.json").write_text(json.dumps(
        {"downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "files": manifest}, indent=2), encoding="utf-8")

    units = pd.concat([pd.read_parquet(BND / f, columns=["unit_id", "name"])
                       for f in ("adm1.parquet", "adm2.parquet")])
    units = units[units["unit_id"].str.match(r"FRA-[12]-")].sort_values("unit_id")
    n1, n2 = units["unit_id"].str.startswith("FRA-1-").sum(), units["unit_id"].str.startswith("FRA-2-").sum()
    if (n1, n2) != (18, 101):
        sys.exit(f"СТОП: в границах {n1} регионов и {n2} департаментов, ожидалось 18 и 101")
    no_cog = sorted(set(units["unit_id"]) - set(cog))
    extra = sorted(set(cog) - set(units["unit_id"]))
    if no_cog or extra:
        sys.exit(f"СТОП: коды не сходятся. Нет в COG: {no_cog}; есть в COG, нет в границах: {extra}")

    today = dt.date.today().isoformat()
    diff = []
    for uid, name in zip(units["unit_id"], units["name"]):
        if nfc(name) != cog[uid]:
            src = FILES["region" if uid.startswith("FRA-1-") else "departement"]
            diff.append({"unit_id": uid, "name_source": name, "name": cog[uid], "source": src,
                         "checked_at": today, "checked_by": SCRIPT})
    new = pd.DataFrame(diff, columns=COLS)

    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    if OVERRIDES.exists():
        old = pd.read_csv(OVERRIDES, dtype=str, keep_default_na=False)
        old = old[~old["unit_id"].str.startswith("FRA-")]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(OVERRIDES, index=False, encoding="utf-8")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rep = REPORT_DIR / f"check_names_cog_{today.replace('-', '')}.md"
    lines = [f"# Названия Франции против COG 2026 · {today}\n",
             f"Сверено: 18 регионов, 101 департамент. Расхождений: **{len(diff)}**.\n",
             "| unit_id | Natural Earth | COG |", "|---|---|---|"]
    lines += [f"| {d['unit_id']} | {d['name_source']} | {d['name']} |" for d in diff]
    lines += ["", "Файлы COG (SHA-256):"] + [f"- {m['file']} — {m['sha256']}" for m in manifest]
    rep.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:4 + len(diff)]))
    print(f"\n{OVERRIDES}\n{rep}")


if __name__ == "__main__":
    main()
