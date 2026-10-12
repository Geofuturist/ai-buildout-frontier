r"""Attribution check by code for the France layers (RES_texts_FRA_layers_v1 §8).

Run from the repo root:
    python scripts\fra\check_licence_phrases_fra.py

For every source, the saved raw pages (research\fra\licences\ and the metadata files next to the
inputs on D:\) are searched for the phrases [RES] listed. Each phrase: FOUND <file> or MISSING.
A MISSING phrase is a stop and a question to [RES]: the attribution is not edited by eye.

Pages missing locally are fetched first if robots.txt allows (data.gouv.fr dataset pages, the
Agence ORE dataset page). Pages that cannot be fetched are listed for V to save by hand
(Ctrl+S, «Web page, HTML only») into research\fra\licences\ under the name shown.
Comparison: HTML entities decoded, tags removed, typographic apostrophes -> ', spaces collapsed.
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
import urllib.request
import urllib.robotparser
from pathlib import Path

REPO = Path.cwd()
LIC = REPO / "research" / "fra" / "licences"
D = Path(r"D:\GISData\Energy\France")
UA = "ABF-observatory/0.1 (research; contact via project)"
OUT = REPO / "research" / "fra" / "licence_phrases_fra.md"

# pages to have locally: name -> url
PAGES = {
    "datagouv_lignes_aeriennes_rte.html": "https://www.data.gouv.fr/datasets/lignes-aeriennes-rte",
    "datagouv_lignes_souterraines_rte_1.html": "https://www.data.gouv.fr/datasets/lignes-souterraines-rte-1",
    "agenceore_6l33py6xpnaolvzkckzkhcic.html": "https://opendata.agenceore.fr/datasets/6l33py6xpnaolvzkckzkhcic",
    "odre_registre_page.html": "https://odre.opendatasoft.com/explore/dataset/"
                               "registre-national-installation-production-stockage-electricite-agrege/information/",
    "odre_lignes_aeriennes_rte_nv_page.html": "https://odre.opendatasoft.com/explore/dataset/lignes-aeriennes-rte-nv/information/",
    "georisques_icpe_page.html": "https://www.georisques.gouv.fr/donnees/bases-de-donnees/installations-industrielles",
}
DATE = {
    "31/07/2026": r"31/07/2026|31 juillet 2026|2026-07-31",
    "10/09/2026": r"10/09/2026|10 septembre 2026|2026-09-10",
    "06/01/2026": r"06/01/2026|6 janvier 2026|2026-01-06",
    "02/11/2023": r"02/11/2023|2 novembre 2023|2023-11-02",
    "30/06/2023": r"30/06/2023|30 juin 2023|2023-06-30",
}
# source -> (files (glob patterns in LIC, or absolute paths), phrases {label: regex})
CHECKS = {
    "ODRÉ registre": (["odre_registre*", str(D / "odre_registre" / "registre_meta.json")], {
        "Licence Ouverte": r"licence ouverte", "2.0": r"2\.0", "31/07/2026": DATE["31/07/2026"],
        "updated 10/09/2026": DATE["10/09/2026"], "RTE": r"\bRTE\b", "Enedis": r"Enedis",
        "EDF SEI": r"EDF SEI", "ELD": r"\bELD\b"}),
    "ODRÉ lignes RTE": (["odre_lignes_aeriennes*", "odre_rte_lignes_aeriennes*",
                         str(D / "odre_rte_lignes" / "lignes-aeriennes-rte-nv_meta.json")], {
        "RTE quote": r"RTE a fait évoluer l'accès aux données GPS des infrastructures du réseau "
                     r"public de transport pour des raisons de sécurité publique"}),
    "Agence ORE": (["agenceore_6l33py6xpnaolvzkckzkhcic*",
                    str(D / "agenceore_consommation" / "6l33py6xpnaolvzkckzkhcic_meta.json")], {
        "Licence Ouverte": r"licence ouverte", "href v1.0": r"Licence_Ouverte\.pdf|2014/05",
        "2024": r"2024", "updated 06/01/2026": DATE["06/01/2026"]}),
    "DDTM lignes aériennes": (["datagouv_lignes_aeriennes_rte*"], {
        "Licence Ouverte / Open Licence version 2.0": r"licence ouverte\s*/\s*open licence version 2\.0",
        "DDTM de l'Eure": r"direction d[ée]partementale des territoires et de la mer de l'eure",
        "02/11/2023": DATE["02/11/2023"], "30/06/2023": DATE["30/06/2023"]}),
    "DDTM lignes souterraines": (["datagouv_lignes_souterraines_rte*"], {
        "Licence Ouverte / Open Licence version 2.0": r"licence ouverte\s*/\s*open licence version 2\.0",
        "DDTM de l'Eure": r"direction d[ée]partementale des territoires et de la mer de l'eure",
        "02/11/2023": DATE["02/11/2023"], "30/06/2023": DATE["30/06/2023"]}),
    "Géorisques": (["georisques*", str(D / "georisques_icpe" / "LICENSE.txt")], {
        "Licence Ouverte": r"licence ouverte|etalab", "2.0": r"2\.0",
        "sauf mention contraire": r"sauf mention contraire"}),
}


def allowed(url: str) -> bool:
    base = "/".join(url.split("/")[:3])
    rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
    try:
        rp.read()
    except Exception:  # noqa: BLE001 - no robots.txt reachable: treat as allowed
        return True
    return rp.can_fetch(UA, url)


def fetch_missing() -> list[str]:
    LIC.mkdir(parents=True, exist_ok=True)
    manual = []
    for name, url in PAGES.items():
        dest = LIC / name
        if dest.exists():
            continue
        if not allowed(url):
            manual.append(f"{name} ← {url} (robots.txt)")
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            print(f"скачано: {name}")
        except Exception as e:  # noqa: BLE001
            manual.append(f"{name} ← {url} ({e})")
    return manual


def text_of(p: Path) -> str:
    raw = p.read_bytes().decode("utf-8", errors="replace")
    if p.suffix == ".json":
        try:
            raw = json.dumps(json.loads(raw), ensure_ascii=False)
        except ValueError:
            pass
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw)) + " " + raw      # raw kept for href checks
    t = unicodedata.normalize("NFC", t).replace("\u2019", "'").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", t)


def main() -> None:
    manual = fetch_missing()
    lines = ["# Проверка атрибуций Франции по сохранённым страницам\n"]
    missing = 0
    for src, (pats, phrases) in CHECKS.items():
        files = []
        for pat in pats:
            if Path(pat).is_absolute():
                files += [Path(pat)] if Path(pat).exists() else []
            else:
                files += sorted(LIC.glob(pat))
        lines.append(f"## {src}\n\nФайлы: " + (", ".join(f"`{f.name}`" for f in files) or "**нет**") + "\n")
        texts = {f: text_of(f) for f in files}
        for label, rx in phrases.items():
            hit = next((f for f, t in texts.items() if re.search(rx, t, re.I)), None)
            missing += hit is None
            lines.append(f"- {label}: " + (f"FOUND `{hit.name}`" if hit else "**MISSING**"))
        lines.append("")
    if manual:
        lines += ["## Сохранить вручную (в research\\fra\\licences\\)\n"] + [f"- {m}" for m in manual]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nОтчёт: {OUT}")
    print(f"MISSING: {missing}" + (" — стоп, вопрос [RES]" if missing else " — все фразы найдены"))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
