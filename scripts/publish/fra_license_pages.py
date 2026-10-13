r"""Check the saved licence pages of the French sources and set the attribution texts of [RES] r5.

[RES] RES_texts_FRA_layers_v1.md r5, section 8: before the final of abf-fra the attributions are checked
by code against the raw HTML saved in research\fra\licences\ (FOUND / MISSING, like license_phrases.py).
A phrase that is not found means STOP and a question to [RES]: the text is never edited by eye.

Run commands (from the repository root, Windows):
    python scripts\publish\fra_license_pages.py check      only look at the pages and write the report
    python scripts\publish\fra_license_pages.py apply      the same, and if nothing is missing, set the texts in the
                                                      four layer yamls (attribution_text, rights_basis, the
                                                      address in known_gaps of RTE). Safe to run again.

The pages are found by their content (the address of the dataset inside the file), so the file names
do not matter. The report is written to research\fra\licences\fra_phrases.txt.
Exit code: 0 all required phrases found, 1 something is missing, 2 the folder is empty or a yaml could not be patched.
"""
from __future__ import annotations

import html as htmllib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from license_phrases import _Links, page_text  # noqa: E402

PAGES_DIR = Path("research") / "fra" / "licences"
REPORT = PAGES_DIR / "fra_phrases.txt"
LAYERS_DIR = Path("layers")
CHECKED_BY = "script:fra_license_pages.py"

# ----------------------------------------------------------------------------- dates
FR_MONTHS = ["janvier", "février|fevrier", "mars", "avril", "mai", "juin", "juillet", "août|aout",
             "septembre", "octobre", "novembre", "décembre|decembre"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]


def date_rx(day: int, month: int, year: int) -> str:
    """Regular expression for one date in the usual forms (day first; ISO; month names in French and English)."""
    d, m, y = f"0?{day}", f"0?{month}", str(year)
    fr, en = FR_MONTHS[month - 1], EN_MONTHS[month - 1]
    en3 = en[:3]
    return "|".join([
        rf"\b{d}\s*[/.\-]\s*{m}\s*[/.\-]\s*{y}\b",
        rf"\b{y}-{m}-{d}(?!\d)",
        rf"\b{d}(?:er)?\s+(?:{fr})\s+{y}\b",
        rf"\b(?:{en}|{en3})\.?\s+{d},?\s+{y}\b",
        rf"\b{d}\s+(?:{en}|{en3})\.?,?\s+{y}\b",
    ])


# ----------------------------------------------------------------------------- what to look for
# Every source: identifier (regex over the raw file; the page is the file that contains it), phrases
# [(label, regex over the visible text, required)]. Section 8 of RES_texts_FRA_layers_v1.md.
SOURCES: list[dict[str, Any]] = [
    {
        "key": "odre_registre", "title": "ODRE, national register",
        "ident": r"registre-national-installation-production-stockage-electricite-agrege",
        "raw_fallback": True,
        "phrases": [
            ("Licence Ouverte 2.0", r"Licence Ouverte.{0,120}?2\.0|Open Licen[cs]e.{0,60}?2\.0", True),
            ("snapshot 31/07/2026", date_rx(31, 7, 2026), True),
            ("updated 10/09/2026", date_rx(10, 9, 2026), True),
            ("RTE", r"\bRTE\b", True), ("Enedis", r"Enedis", True),
            ("EDF SEI", r"EDF SEI", True), ("ELD", r"\bELD\b", True),
        ],
    },
    {
        "key": "odre_lignes", "title": "ODRE, RTE overhead lines (nv)",
        "ident": r"lignes-aeriennes-rte-nv",
        "phrases": [
            ("sentence on GPS data",
             r"RTE a fait évoluer l'accès aux données GPS des infrastructures du réseau public de transport "
             r"pour des raisons de sécurité publique", True),
        ],
        "address": True,
    },
    {
        "key": "agenceore", "title": "Agence ORE, consumption by department",
        "ident": r"6l33py6xpnaolvzkckzkhcic",
        "phrases": [
            ("Licence Ouverte", r"Licence Ouverte", True),
            ("2024", r"\b2024\b", True),
            ("updated 06/01/2026", date_rx(6, 1, 2026), True),
        ],
        "href_v1": True,
    },
    {
        "key": "agenceore_region", "title": "Agence ORE, consumption by region (v0.2.0)",
        "ident": r"8us2i1a0pj4rtmhil0z42yzu",
        "phrases": [
            ("Licence Ouverte / Open Licence", r"Licence Ouverte\s*/\s*Open Licen[cs]e", True),
            ("updated 10/03/2026", date_rx(10, 3, 2026), True),
        ],
        "href_v2": True,
    },
    {
        "key": "ddtm_aeriennes", "title": "DDTM, Lignes aeriennes RTE (data.gouv.fr)",
        "ident": r"lignes-aeriennes-rte(?![-\w])",
        "phrases": [
            ("Licence Ouverte / Open Licence version 2.0",
             r"Licence Ouverte\s*/\s*Open Licen[cs]e version 2\.0", True),
            ("producer DDTM de l'Eure", r"Direction D[ée]partementale des Territoires et de la Mer de l'Eure", True),
            ("updated 2 November 2023", date_rx(2, 11, 2023), True),
            ("data as of 30 June 2023", date_rx(30, 6, 2023), True),
        ],
    },
    {
        "key": "ddtm_souterraines", "title": "DDTM, Lignes souterraines RTE (data.gouv.fr)",
        "ident": r"lignes-souterraines-rte-1",
        "phrases": [
            ("Licence Ouverte / Open Licence version 2.0",
             r"Licence Ouverte\s*/\s*Open Licen[cs]e version 2\.0", True),
            ("producer DDTM de l'Eure", r"Direction D[ée]partementale des Territoires et de la Mer de l'Eure", True),
            ("updated 2 November 2023", date_rx(2, 11, 2023), True),
            ("data as of 30 June 2023", date_rx(30, 6, 2023), True),
        ],
    },
    {
        "key": "georisques", "title": "Georisques (LICENSE.txt and the ICPE download page)",
        "ident": r"georisques",
        "skip_files": r"datagouv",
        "phrases": [
            ("Licence Ouverte 2.0 / etalab",
             r"Licence Ouverte.{0,120}?(?:2\.0|etalab)|etalab-2\.0", True),
            ("'unless otherwise indicated'",
             r"sauf mention contraire|sauf indication contraire|sauf mention expresse|unless otherwise (?:indicated|stated)", True),
        ],
    },
]

# ----------------------------------------------------------------------------- texts of [RES] r5
LIC2 = "Licence Ouverte / Open Licence version 2.0"
LIC1 = "Licence Ouverte / Open Licence v1.0"
RTE_GAP_1 = ("The line geometry dates from 30 June 2023 (a public copy republished by DDTM de l'Eure). Since June "
             "2026 RTE publishes its list of lines on ODRÉ without coordinates, citing public security: "
             "\"RTE a fait évoluer l'accès aux données GPS des infrastructures du réseau public de transport pour "
             "des raisons de sécurité publique\" (ODRÉ, Lignes aériennes RTE, {url}). The project therefore "
             "publishes only department totals and does not publish line segments.")
RES_URL_RTE_NV = "https://odre.opendatasoft.com/explore/dataset/lignes-aeriennes-rte-nv/information/"

# layer yaml -> (source_id, {path: value}); the value of rights_basis checked_at / checked_by is added at apply time
EDITS: dict[str, tuple[str, dict[tuple[str, ...], str]]] = {
    "energy_generation_odre_adm2": ("odre_registre", {
        ("license", "name"): LIC2,
        ("license", "attribution_text"):
            "Generation: Registre national des installations de production et de stockage d'électricité "
            "(au 31/07/2026), RTE, Enedis, EDF SEI and local distribution companies (ELD), published on Open Data "
            "Réseaux Énergies (ODRÉ), last updated 10/09/2026, " + LIC2 + ".",
        ("rights_basis", "text"): "The metadata of the ODRÉ dataset page state " + LIC2 + ".",
    }),
    "energy_consumption_agenceore_adm2": ("agenceore_conso_dept", {
        ("license", "name"): LIC1,
        ("license", "attribution_text"):
            "Consumption: Agence ORE, Consommation annuelle d'électricité et gaz par département, last updated "
            "06/01/2026, " + LIC1 + ".",
        ("rights_basis", "text"):
            "The dataset page on the Agence ORE portal states \"Licence Ouverte / Open Licence\" and links to "
            "version 1.0 of its text.",
    }),
    # v0.2.0, Agence ORE by region (RES r3, r4 section 7): version 2.0 and date 10/03/2026 from the saved page
    "energy_consumption_agenceore_adm1": ("agenceore_conso_region", {
        ("license", "name"): LIC2,
        ("license", "attribution_text"):
            "Consumption by region: Agence ORE, Consommation annuelle d'électricité et gaz par région, last "
            "updated 10/03/2026, " + LIC2 + ".",
        ("rights_basis", "text"):
            "The dataset page on the Agence ORE portal states \"" + LIC2 + "\" and gives 10 March 2026 as the "
            "date of the last data update.",
    }),
    "energy_transmission_rte_adm2": ("rte_lignes_ddtm27", {
        ("license", "name"): LIC2,
        ("license", "attribution_text"):
            "Transmission lines: Lignes aériennes RTE and Lignes souterraines RTE (network of RTE, data as of "
            "30/06/2023), Direction départementale des territoires et de la mer de l'Eure, data.gouv.fr, last "
            "updated 02/11/2023, " + LIC2 + ".",
        ("rights_basis", "text"):
            "The data.gouv.fr pages of both datasets state " + LIC2 + ". The line segments are withheld by the "
            "project's rule on geometry withdrawn by its operator, not by the license.",
    }),
    "dc_icpe_georisques": ("georisques_icpe", {
        ("license", "name"): LIC2,
        ("license", "attribution_text"):
            "Data centers: selected from Installations classées pour la protection de l'environnement (ICPE), "
            "Géorisques, extract downloaded 10/10/2026, " + LIC2 + ".",
        ("rights_basis", "text"):
            "The Géorisques site states that, unless otherwise indicated, its content is under the license etalab-2.0, "
            "which is " + LIC2 + ".",
    }),
}


# ----------------------------------------------------------------------------- reading the pages
def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def visible(raw_text: str) -> str:
    """Visible text for html, normalised text for anything else."""
    if re.search(r"<(html|body|div|a|p|span)[\s>]", raw_text, re.I):
        return page_text(raw_text.encode("utf-8"))
    text = " ".join(raw_text.split())
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")


def saved_address(raw_text: str, sidecar: str) -> list[str]:
    """Addresses the saved page was taken from: browser comment, canonical link, og:url, sidecar line."""
    found: list[str] = []
    for rx in (r"saved from url=\(\d+\)\s*(\S+)",
               r"<link[^>]+rel=[\"']canonical[\"'][^>]*href=[\"']([^\"']+)",
               r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]*rel=[\"']canonical[\"']",
               r"<meta[^>]+property=[\"']og:url[\"'][^>]*content=[\"']([^\"']+)"):
        found += [m.strip() for m in re.findall(rx, raw_text, re.I)]
    found += [m.group(2) for m in re.finditer(r"^(url|address|adresse)\s*[:=]\s*(\S+)", sidecar, re.I | re.M)]
    return [f for f in dict.fromkeys(found) if f.startswith("http")]


def norm_url(url: str) -> str:
    u = re.sub(r"^https?://", "", url.strip().lower())
    u = re.sub(r"^www\.", "", u)
    return re.split(r"[?#]", u)[0].rstrip("/")


def collect_files() -> list[Path]:
    files = [p for p in sorted(PAGES_DIR.rglob("*")) if p.is_file() and p.suffix.lower() in (".html", ".htm", ".txt", ".md", ".json")
             and p.name != REPORT.name]
    for extra in sorted(Path("research", "fra").glob("**/LICENSE*.txt")):
        if extra not in files and PAGES_DIR not in extra.parents:
            files.append(extra)
    return files


def check() -> tuple[list[str], list[str], dict[str, Any]]:
    """Returns report lines, names of missing required items, and facts for apply (saved address of the RTE page)."""
    files = collect_files()
    if not files:
        return [f"STOP: no files in {PAGES_DIR}"], ["no files"], {}
    docs = {p: read_text_file(p) for p in files}
    lines = [f"checked (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
             f"files in {PAGES_DIR}: {len(files)}", ""]
    for p in files:
        lines.append(f"  file {p}")
    lines.append("")
    missing: list[str] = []
    facts: dict[str, Any] = {}
    for src in SOURCES:
        lines.append(f"=== {src['title']}")
        pages = [p for p in files if re.search(src["ident"], docs[p] + " " + p.name, re.I)
                 and not (src.get("skip_files") and re.search(src["skip_files"], p.name, re.I))]
        if not pages:
            lines.append(f"MISSING page: no saved file contains {src['ident']}")
            missing.append(f"{src['key']}: page")
            lines.append("")
            continue
        lines.append("pages: " + "; ".join(str(p) for p in pages))
        text = " ".join(visible(docs[p]) for p in pages)
        # Raw html with entities decoded: the metadata that portals embed as json in the page source.
        rawtext = " ".join(htmllib.unescape(docs[p]).replace("\\", "") for p in pages) if src.get("raw_fallback") else ""
        for label, rx, required in src["phrases"]:
            m = re.search(rx, text, re.I)
            if m:
                lo, hi = max(0, m.start() - 160), min(len(text), m.end() + 160)
                lines.append(f"FOUND   {label}: ...{text[lo:hi]}...")
                continue
            m = re.search(rx, rawtext, re.I) if rawtext else None
            if m:
                lo, hi = max(0, m.start() - 100), min(len(rawtext), m.end() + 100)
                lines.append(f"FOUND   {label} [in page source metadata, not in visible text]: ...{rawtext[lo:hi]}...")
            else:
                lines.append(f"MISSING {label} ({'required' if required else 'optional'}): {rx}")
                if required:
                    missing.append(f"{src['key']}: {label}")
        if src.get("href_v1"):
            hrefs: list[str] = []
            for p in pages:
                parser = _Links()
                parser.feed(docs[p])
                hrefs += [h for _t, h in parser.links if re.search(r"licen[cs]e|etalab", h, re.I)]
            hrefs = list(dict.fromkeys(hrefs))
            lines.append(f"licence link(s) found: {hrefs}")
            ok = [h for h in hrefs if re.search(r"licence[-_]ouverte|licence-ouverte", h, re.I) and not re.search(r"2\.0|v2", h, re.I)]
            if ok:
                lines.append(f"FOUND   link to the text of version 1.0: {ok[0]}")
            else:
                lines.append("MISSING link to the text of version 1.0 (required): no href with Licence Ouverte that is not 2.0")
                missing.append(f"{src['key']}: link to version 1.0")
        if src.get("href_v2"):
            links2: list[tuple[str, str]] = []
            for p in pages:
                parser = _Links()
                parser.feed(docs[p])
                links2 += [(t, h) for t, h in parser.links if re.search(r"licen[cs]e|etalab", h + " " + t, re.I)]
            links2 = list(dict.fromkeys(links2))
            lines.append(f"licence link(s) found (text -> href): {links2}")
            # The version is read from the link itself: its label ("... version 2.0") or its address.
            ok2 = [(t, h) for t, h in links2
                   if re.search(r"Licence Ouverte\s*/\s*Open Licen[cs]e\s+version 2\.0", t, re.I) or re.search(r"2\.0|v2", h, re.I)]
            if ok2:
                lines.append(f"FOUND   link to the licence with version 2.0: label '{ok2[0][0]}' -> {ok2[0][1]}")
            else:
                lines.append("MISSING link to the licence with version 2.0 (required): no link whose label or address says 2.0")
                missing.append(f"{src['key']}: link to version 2.0")
        if src.get("address"):
            sidecars = " ".join(read_text_file(p.with_suffix(".txt")) for p in pages if p.suffix.lower() != ".txt" and p.with_suffix(".txt").exists())
            addrs: list[str] = []
            for p in pages:
                addrs += saved_address(docs[p], sidecars)
            addrs = list(dict.fromkeys(addrs))
            lines.append(f"saved page address candidates: {addrs}")
            if not addrs:
                lines.append("MISSING address of the saved page (required): no 'saved from url', canonical link or URL line")
                missing.append(f"{src['key']}: address of the saved page")
            else:
                best = next((a for a in addrs if "lignes-aeriennes-rte-nv" in a), addrs[0])
                facts["rte_url"] = best
                if norm_url(best) == norm_url(RES_URL_RTE_NV):
                    lines.append(f"FOUND   address equals the address of [RES]: {best}")
                else:
                    lines.append(f"DIFFERENT address: saved {best} / [RES] {RES_URL_RTE_NV}; the saved one goes into known_gaps")
        lines.append("")
    return lines, missing, facts


# ----------------------------------------------------------------------------- patching the yamls
def yq(value: str) -> str:
    """Single-quoted yaml scalar on one line."""
    return "'" + value.replace("'", "''") + "'"


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block_end(lines: list[str], start: int, indent: int) -> int:
    """First line after `start` that is not deeper than `indent` (blank lines stay inside)."""
    i = start + 1
    while i < len(lines) and (not lines[i].strip() or indent_of(lines[i]) > indent):
        i += 1
    while i > start + 1 and not lines[i - 1].strip():
        i -= 1
    return i


def find_source(lines: list[str], source_id: str) -> tuple[int, int, int]:
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)- source_id:\s*{re.escape(source_id)}\s*$", line)
        if m:
            n = len(m.group(1))
            end = i + 1
            while end < len(lines) and (not lines[end].strip() or indent_of(lines[end]) > n):
                end += 1
            return i, end, n + 2
    raise KeyError(f"source_id {source_id} not found")


def set_key(lines: list[str], lo: int, hi: int, key_indent: int, path: tuple[str, ...], value: str) -> bool:
    """Set the scalar at `path` below lines[lo:hi]; True if the text changed."""
    for depth, key in enumerate(path):
        ind = key_indent + 2 * depth
        idx = next((j for j in range(lo, hi) if re.match(rf"^ {{{ind}}}{re.escape(key)}:", lines[j])), None)
        if idx is None and depth == len(path) - 1:  # the last key may be new: add it at the end of its block
            at = hi
            while at > lo and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, " " * ind + f"{key}: {value}")
            return True
        if idx is None:
            raise KeyError(f"key {'.'.join(path[:depth + 1])} not found")
        if depth == len(path) - 1:
            new = " " * ind + f"{key}: {value}"
            end = block_end(lines, idx, ind)
            if lines[idx:end] == [new]:
                return False
            lines[idx:end] = [new]
            return True
        lo, hi = idx + 1, block_end(lines, idx, ind)
    return False


def patch_layer(layer_id: str, source_id: str, values: dict[tuple[str, ...], str], rte_url: str | None,
                today: str) -> list[str]:
    path = LAYERS_DIR / f"{layer_id}.yaml"
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    log: list[str] = []
    lo, hi, key_ind = find_source(lines, source_id)
    todo = dict(values)
    todo[("rights_basis", "checked_at")] = today
    todo[("rights_basis", "checked_by")] = CHECKED_BY
    for p, v in todo.items():
        lo, hi, key_ind = find_source(lines, source_id)  # lines shift after each edit
        changed = set_key(lines, lo, hi, key_ind, p, yq(v))
        log.append(f"  {'changed' if changed else 'already'}  {source_id}.{'.'.join(p)}")
    if layer_id == "energy_transmission_rte_adm2":
        assert rte_url
        new_gap = RTE_GAP_1.format(url=rte_url)
        gi = next(j for j, l in enumerate(lines) if re.match(r"^\s*known_gaps:\s*$", l) and indent_of(l) == 2)
        item = gi + 1
        while not lines[item].strip():
            item += 1
        m = re.match(r"^(\s*)- ", lines[item])
        if not m or len(m.group(1)) != 2:
            raise KeyError("first known_gaps item of RTE not found")
        end = block_end(lines, item, 2)
        new = "  - " + yq(new_gap)
        changed = lines[item:end] != [new]
        lines[item:end] = [new]
        log.append(f"  {'changed' if changed else 'already'}  known_gaps[0] (address {rte_url})")
    text = eol.join(lines)
    # verify with a real yaml parser before writing
    doc = yaml.safe_load(text)
    src = next(s for s in doc["sources"] if s["source_id"] == source_id)
    for p, v in values.items():
        node: Any = src
        for k in p:
            node = node[k]
        if node != v:
            raise ValueError(f"{layer_id}: {'.'.join(p)} is not as intended after the patch")
    if layer_id == "energy_transmission_rte_adm2" and doc["coverage"]["known_gaps"][0] != RTE_GAP_1.format(url=rte_url):
        raise ValueError(f"{layer_id}: known_gaps[0] is not as intended after the patch")
    path.write_bytes(text.encode("utf-8"))
    return log


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("check", "apply"):
        print("usage: python scripts\\publish\\fra_license_pages.py check|apply")
        return 2
    lines, missing, facts = check()
    if not PAGES_DIR.exists():
        print(f"STOP: folder {PAGES_DIR} not found; run from the repository root")
        return 2
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(l[:230] for l in lines if l.startswith(("FOUND", "MISSING", "DIFFERENT", "===", "STOP", "pages:"))))
    print(f"\nreport: {REPORT}")
    if missing:
        print("\nSTOP: not found (ask [RES], do not edit the texts by eye):")
        for m in missing:
            print("  -", m)
        return 1
    print("\nAll required phrases FOUND.")
    if argv[1] == "check":
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for layer_id, (source_id, values) in EDITS.items():
        try:
            for l in patch_layer(layer_id, source_id, values, facts.get("rte_url"), today):
                print(l)
        except (KeyError, ValueError) as exc:
            print(f"STOP {layer_id}: {exc}; the file was not changed")
            return 2
    print("\nTexts set. Next: rebuild dev, then git add layers.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
