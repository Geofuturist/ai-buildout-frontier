r"""Check the phrases of the abf-energy and abf-energync texts against the About sheets of the GEM file (RES_texts_GEM_v0_1_0.md r1, section 10 item 1).

The public texts quote GEM's own words (licence, attribution, definitions). Before the final build every phrase must be
found, by code, in the text of the GEM workbook and in the layer yamls; a phrase that is not found means STOP and a
question to [RES]. The text is never edited by eye.

Run command (from the repository root, Windows; the path of the xlsx is the file whose SHA-256 is in build_hashes.json):
    python scripts\publish\check_gem_phrases.py --xlsx "D:\GISData\AI\GEM\Global Integrated Power September 2026 V2.xlsx"

What it does:
  1. reads every sheet of the workbook except the big data sheet (Power facilities) as text, quotes, dashes and spaces
     normalized, capitals do not matter;
  2. looks for each phrase in that text;
  3. checks that the layer yamls (the four GEM layers) contain the phrase word for word, so the text and the check cannot
     drift apart;
  4. prints FOUND / MISSING for each phrase and writes the same to --report (default: gem_phrases.txt in the current folder).
Exit code: 0 all phrases found, 1 something is missing, 2 the workbook or a yaml is not found.
Also used by build_release.py (release yaml key phrase_check: {kind: gem, xlsx: ..., layers: ...}).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from common import iter_strings  # noqa: E402

LAYER_YAMLS = ("energy_plants_gem_units.yaml", "energy_plants_gem_locations.yaml",
               "energy_plants_gem_tzsam_units.yaml", "energy_plants_gem_tzsam_locations.yaml")
DATA_SHEET = "power facilities"     # the sheet with 183,404 units: not read (slow, not a text sheet)
MAX_ROWS_PER_SHEET = 3000           # a text sheet is short; a longer one is a data sheet

# (key, phrase, searched in the workbook?)  Phrases are substrings, word for word (RES_texts_GEM r1 section 10 item 1).
PHRASES: list[tuple[str, str, bool]] = [
    ("gem_copyright",
     "Copyright © Global Energy Monitor. Global Integrated Power Tracker, September 2026 release. Distributed under a "
     "Creative Commons Attribution 4.0 International License.", True),
    ("gem_tz_id",
     "records with a “TZ ID” in the Other IDs (unit/phase) column were partially or fully sourced from the "
     "TransitionZero, Solar Asset Mapper, August 2025.", True),
    ("tz_copyright",
     "Copyright © TransitionZero, Solar Asset Mapper, August 2025. Distributed under a Creative Commons "
     "Attribution-Non-Commercial 4.0 International License (CC BY-NC 4.0).", True),
    ("gem_citation", "Global Energy Monitor, Global Integrated Power Tracker, September 2026 release.", True),
    ("capacity_definition", "Total nameplate capacity, or best available data, of the project, in megawatts", True),
    ("country_area_note",
     "presents energy data within various economic contexts, and the geographical unit does not strictly follow "
     "political boundaries", True),
    ("location_accuracy",
     "Approximate based on using nearest city or other information in research, or exact based on visibility on map "
     "or given in research", True),
    ("pumped_storage",
     "The project generates electricity using water which is cycled between a lower and an upper reservoir by a "
     "pumping system.", True),
    ("solar_ac_dc",
     "Capacity may be reported as the DC / peak value the arrays could provide or as the AC value of what will be "
     "tied into the grid. This is often not specified and could be either value when reported as just 'MW'.", True),
    ("inferred_progress", "lack of observed progress", True),
    ("captive_facilities", "within industrial facilities", True),
    ("captive_supply", "typically supply most of their power", True),
    ("dc_ppa", "connected to a data center through a PPA", True),
    # a value of the data sheet, not a phrase of the About sheet: only the yaml is checked
    ("assumed_pv", "Assumed PV", False),
]


def norm(text: str) -> str:
    """Quotes, dashes and spaces in one form (no space before punctuation); lower case."""
    t = (text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-").replace("\u00a0", " "))
    t = " ".join(t.split())
    return re.sub(r"\s+([.,;:!?])", r"\1", t).lower()


def workbook_text(xlsx: Path) -> tuple[str, list[str]]:
    """Normalized text of every sheet except the data sheet; the names of the sheets read."""
    from openpyxl import load_workbook   # imported here: the other scripts of the folder do not need it

    wb = load_workbook(xlsx, read_only=True, data_only=True)
    parts: list[str] = []
    read: list[str] = []
    try:
        for ws in wb.worksheets:
            if ws.title.strip().lower() == DATA_SHEET:
                continue
            read.append(ws.title)
            for n, row in enumerate(ws.iter_rows(values_only=True)):
                if n >= MAX_ROWS_PER_SHEET:
                    break
                parts += [str(v) for v in row if v is not None]
    finally:
        wb.close()
    return norm(" ".join(parts)), read


def yaml_text(layers_dir: Path) -> tuple[str, list[str]]:
    """All strings of the four GEM layer yamls as one normalized text; the names of yamls that are missing."""
    parts, missing = [], []
    for name in LAYER_YAMLS:
        path = layers_dir / name
        if not path.exists():
            missing.append(name)
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        parts += [s for _, s in iter_strings(data)]
    return norm(" ".join(parts)), missing


def run_check(xlsx: Path, layers_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """-> (report lines, phrases not found, problems that stop the check: workbook or yamls missing)."""
    lines: list[str] = []
    not_found: list[str] = []
    problems: list[str] = []
    ytext, ymissing = yaml_text(layers_dir)
    if ymissing:
        problems.append(f"layer yamls not found in {layers_dir}: {ymissing}")
    if not xlsx.exists():
        problems.append(f"GEM workbook not found: {xlsx}")
        return lines + [f"NO FILE  {xlsx}"], not_found, problems
    wtext, sheets = workbook_text(xlsx)
    lines.append(f"sheets read: {sheets}")
    for key, phrase, in_book in PHRASES:
        needle = norm(phrase)
        hit = needle in wtext if in_book else True
        state = "FOUND  " if hit else "MISSING"
        if not hit:
            not_found.append(key)
        extra = ""
        if not ymissing:
            if needle in ytext:
                extra = "  [yaml quotes it]"
            else:
                extra = "  [YAML DOES NOT CONTAIN IT]"
                not_found.append(f"{key} (yaml)")
        lines.append(f"{state} {key}{'' if in_book else ' (data value, workbook not searched)'}{extra}")
        if hit and in_book:
            i = wtext.index(needle)
            lines.append(f"         ...{wtext[max(0, i - 60): i + len(needle) + 60]}...")
    return lines, not_found, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the quoted phrases of the GEM texts against the GEM workbook and the layer yamls.")
    ap.add_argument("--xlsx", required=True, type=Path, help="the GEM workbook (Global Integrated Power September 2026 V2.xlsx)")
    ap.add_argument("--layers", type=Path, default=Path("layers"), help="folder with the layer yamls (default: layers)")
    ap.add_argument("--report", type=Path, default=Path("gem_phrases.txt"))
    args = ap.parse_args()
    lines, not_found, problems = run_check(args.xlsx, args.layers)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [f"GEM phrase check {stamp}", f"workbook: {args.xlsx}", *lines]
    if problems:
        out += ["", "PROBLEMS:", *problems]
    if not_found:
        out += ["", f"NOT FOUND: {not_found}"]
    args.report.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(out))
    if problems:
        return 2
    return 1 if not_found else 0


if __name__ == "__main__":
    sys.exit(main())
