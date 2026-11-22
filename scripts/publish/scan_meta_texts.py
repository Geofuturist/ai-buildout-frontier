r"""Scan the built meta.json files of a release for words and patterns that must not be in public texts.

Run command (from the repository root, Windows):
    python scripts\publish\scan_meta_texts.py "D:\GISData\release\abf-layers-v0.1.0" "D:\GISData\release\abf-boundaries-v0.1.0"

Looks for: British spelling (licence, kilometre), [RES], {placeholders} outside citation templates,
"0 more", and the wrong spellings "License Ouverte" / "Open License" / "open_license".
Cyrillic (always checked, A-062): no Cyrillic letter in any public text of the release folder. Public texts are the meta.json files,
manifest.json, index/*/build_meta.json, listing.json and every other .json / .csv / .txt / .md / .geojson file of the folder except
(a) the data files of the layers (<layer_id>.csv, .parquet, .geojson, .csv.gz: source records may keep original-script names, and the build
checks their columns itself, G7), (b) the files that are not published (build_log.json, build_plan.json, release_report.md, zenodo_files.txt,
the country files and archives of an index). The one allowed place is the field title_ru of a meta.json (G7).
The names "Licence Ouverte" / "Open Licence" / "International Licence" (the Atlas title of CC BY 4.0), the code open_licence and script names (script:06_licences.py) are allowed; so are the {n} of display.unit_card_line and the {field} slots of display.popup and display.popup_title (filled in by the site). Nothing is changed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED = re.compile(r"open_licence|Licence\s+Ouverte|Open\s+Licence|International\s+Licence|https?://\S+|script:\S+", re.I)  # names, the code, URLs and script names may keep the British spelling; "International Licence" is the Atlas title of CC BY 4.0, quoted in rights_basis (abf-dc)
CHECKS = [
    ("licence (British spelling)", re.compile(r"licen[c]e", re.I), True),
    ("kilometre", re.compile(r"kilomet(re|res)\b", re.I), False),
    ("[RES] marker", re.compile(r"\[RES\]"), False),
    ("'0 more'", re.compile(r"\b0 more\b"), False),
    ("wrong 'License Ouverte'", re.compile(r"License\s+Ouverte"), False),
    ("wrong 'Open License'", re.compile(r"Open\s+License"), False),
    ("wrong 'open_license'", re.compile(r"open_license"), False),
]
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
CYRILLIC = re.compile("[\u0400-\u04FF]")
CYRILLIC_ALLOWED_PATHS = ("title_ru",)          # G7: the Russian title of a layer is the one place with Cyrillic
NOT_PUBLISHED = {"build_log.json", "build_plan.json", "release_report.md", "zenodo_files.txt", ".abf_release_dir"}
TEXT_SUFFIXES = {".json", ".csv", ".txt", ".md", ".geojson"}
LAYER_DATA_SUFFIXES = (".csv", ".csv.gz", ".parquet", ".geojson", ".geojson.gz")
POPUP_TEXT = re.compile(r"display\.popup\[\d+\]\.text$")   # {field} of display.popup: filled in by the site from the properties of the object (abf-energy)


def walk(node, path=""):  # noqa: ANN001, ANN201
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def layer_ids(root: Path) -> set[str]:
    """Ids of the layers of a release folder: the names of its <layer_id>.meta.json files."""
    return {f.name[: -len(".meta.json")] for f in root.glob("*.meta.json")}


def public_text_files(root: Path) -> list[Path]:
    """Text files of the release folder that the Cyrillic check reads (see the docstring)."""
    ids = layer_ids(root)
    out: list[Path] = []
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = f.relative_to(root)
        if f.name in NOT_PUBLISHED or f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if len(rel.parts) == 1 and any(f.name == i + suf for i in ids for suf in LAYER_DATA_SUFFIXES):
            continue                                   # data file of a layer
        if rel.parts[0] == "index" and len(rel.parts) > 3 and rel.parts[2] not in ("rules",):
            continue                                   # country files and the like inside an index folder
        out.append(f)
    return out


def cyrillic_problems(root: Path) -> tuple[int, int]:
    """Print every place with Cyrillic in the public texts of the folder; return (files checked, problems)."""
    total = 0
    files = public_text_files(root)
    for f in files:
        name = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8-sig")
        if f.suffix.lower() == ".json":
            for path, value in walk(json.loads(text)):
                if CYRILLIC.search(value) and path not in CYRILLIC_ALLOWED_PATHS:
                    flat = " ".join(value.split())
                    print(f"FOUND Cyrillic: {name} {path}: ...{flat[:120]}...")
                    total += 1
        else:
            for ln, line in enumerate(text.splitlines(), start=1):
                m = CYRILLIC.search(line)
                if m:
                    print(f"FOUND Cyrillic: {name} line {ln}: ...{line[max(0, m.start() - 40):m.start() + 40]}...")
                    total += 1
    return len(files), total


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    total = 0
    for folder in argv[1:]:
        root = Path(folder)
        # the meta.json of a release of layers/boundaries, and the public meta.json of every territory index (index/<set>/meta.json)
        for f in sorted(root.glob("*.meta.json")) + sorted(root.glob("index/*/meta.json")):
            name = f.relative_to(root).as_posix()
            meta = json.loads(f.read_text(encoding="utf-8"))
            for path, text in walk(meta):
                flat = " ".join(text.split())
                cleaned = ALLOWED.sub("", flat)
                for label, rx, use_cleaned in CHECKS:
                    if rx.search(cleaned if use_cleaned else flat):
                        print(f"FOUND {label}: {name} {path}: ...{flat[:120]}...")
                        total += 1
                if "citation" not in path and path != "totals_note" and not path.endswith(("display.unit_card_line", "display.list_title", "display.popup_title")) and not POPUP_TEXT.search(path) and PLACEHOLDER.search(flat):  # {n}: filled in by the site (abf-dc); totals_note of an index: {index_file}, {version} are the site's
                    print(f"FOUND placeholder: {name} {path}: ...{flat[:120]}...")
                    total += 1
            print(f"checked {name}")
        n_files, n_cyr = cyrillic_problems(root)
        total += n_cyr
        print(f"Cyrillic check: {n_files} public text files of {root.name}, {n_cyr} problems")
    print(f"\nProblems found: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
