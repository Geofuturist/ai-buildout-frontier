r"""Patch layers\abf_boundaries.yaml for the release abf-boundaries v0.2.0 (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\patch_bnd_v020.py            # shows what would change, writes nothing
    python scripts\publish\patch_bnd_v020.py --apply    # writes the file

What it does (texts of RES_texts_BND_v0_2_0.md section 3, r5 of 18 October):
  - replaces the top-level blocks: description, published_columns, fields, coverage, verification, display, tiles;
  - sets the attribution text of the source natural_earth;
  - adds the source unicode_cldr at the end of sources (if it is not there).
Everything else (header, license, freshness, citation, the other sources) is kept byte for byte, line endings too.
The shares of verification (sample_share, agent_sample) are NOT written here: the build computes them from the registry.
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path

YAML_PATH = Path("layers") / "abf_boundaries.yaml"

DESCRIPTION = (
    "Administrative units of the world: countries (ADM0) everywhere, first-level units (ADM1) for 108 countries and "
    "second-level units (ADM2) for the United States, France and Norway, in the countries whose entry in the boundary "
    "registry has been verified. Every unit has a code unit_id: ISO3 for countries, ISO3-level-national code below them "
    "(for example USA-2-51059 or POL-1-24). Units carry the geometry used on the map; for the United States and Norway, "
    "the national geometry used for calculations is published in separate analysis files. Boundaries follow the U.S. "
    "government's point of view, with one rule-based exception, and do not express a position of the project. The "
    "exception: where sources show that another recognized state controls whole units of the frame and has made them part "
    "of its own administrative division, the frame shows the state in control. In this release this applies to Crimea and "
    "Sevastopol, shown under Russia. The contested_areas layer lists areas of disputed control: the state in control, the "
    "state that claims the area, the date from which control is counted, and the sources for both. Areas that the U.S. "
    "point of view assigns to no country are a separate layer. Changes from 0.1.0: ADM1 added for 104 countries (1,578 "
    "units) by the top level of ISO 3166-2 in Unicode CLDR release-48-2, with documented corrections; Adjara added to the "
    "ADM0 unit of Georgia (GEO), which Natural Earth 1:10m v5.1.2 (U.S. point of view) left uncovered; Crimea and "
    "Sevastopol shown under Russia instead of Ukraine, by the rule above; six French region and department names aligned "
    "with the official geographic code of INSEE (COG); new layer contested_areas."
)

GEOGRAPHY = ("World (ADM0); ADM1 for 108 countries and ADM2 for the United States, France and Norway, the countries "
             "with a verified entry in the boundary registry")

KNOWN_GAPS = [
    "Ten areas, about 487 km² together, belong to a country but to none of its first-level units, because Natural Earth "
    "gives them no code of the reference list: six in Australia (Jervis Bay Territory, Christmas Island, the Cocos "
    "(Keeling) Islands, Macquarie Island, Ashmore and Cartier Islands, the Coral Sea Islands), two in the United Arab "
    "Emirates, one in Russia and one in Venezuela. They are listed with their areas in adm1_leftovers.csv. Macquarie "
    "Island is left out of Tasmania (AUS-1-TAS) until it is checked against a document of the state.",
    "Thirteen small areas of land in the Natural Earth admin-1 file, from 1 to 45 km² each and about 289 km² together, "
    "are covered by no ADM0 unit and are not in the layer of unassigned areas either. Most are coastal edges and small "
    "islands where the admin-1 and admin-0 files of Natural Earth are drawn differently; one is the Paracel Islands "
    "(5 km²). They are listed in validation_report.json.",
    "ADM1 follows the top level of ISO 3166-2 as recorded in Unicode CLDR release-48-2; reforms after that release may "
    "not be reflected.",
    "First-level units are cut to the outline of their country. Where Natural Earth draws a first-level unit beyond that "
    "outline, the part outside is left out; the largest is 2,268 km² of Ladakh (IND-1-LA) inside the outline of China in "
    "the U.S. point of view. All such losses are listed in validation_report.json.",
    "ADM1 units exist only for countries whose registry entry has been verified (108 in this release); ADM2 units exist "
    "for the United States, France and Norway. The other 134 countries and territories have ADM0 only.",
    "First-level units outside the United States and Norway, and the departments of France, are built from Natural Earth "
    "1:10m units. They are generalized and are not the official national boundaries.",
    "Disputed and unassigned areas are not part of any country.",
    "The frame departs from the U.S. point of view only for whole units of the frame that another recognized state "
    "controls and has made part of its own administrative division, as shown by sources: Crimea and Sevastopol, shown "
    "under Russia, with Ukraine's claim in the contested_areas layer. Areas of the Donetsk, Luhansk, Zaporizhzhia and "
    "Kherson regions under Russian control since 2022 remain under Ukraine: the rule applies only to whole units, and no "
    "open dated line of control was found. Other areas of disputed control have not yet been checked against this rule.",
    "The contested_areas layer lists only areas whose control has been checked against sources: Crimea and Sevastopol in "
    "this release.",
    "The first-level codes of Crimea (RUS-1-35) and Sevastopol (RUS-1-67) are codes of Russia's OKATO classifier, not "
    "ISO 3166-2 codes: ISO 3166-2 lists these units under Ukraine (UA-43, UA-40).",
    "For first-level units added in version 0.2.0, unit_type_local and unit_type_en give the types of first-level units "
    "in the country, not the type of each unit. In 29 countries with more than one type, such as states and a federal "
    "district, all types are listed, separated by \"/\". In 21 countries the types are not filled in this release. The "
    "type of each unit is planned for a later version.",
]

VERIFICATION_METHOD = (
    "Units are built by script from the sources by the method named in the registry; the registry marks a country and "
    "level as verified before its units are published. For the first-level units added in version 0.2.0, the code list "
    "of each country was matched to Unicode CLDR release-48-2 by script, and a random sample of countries, together with "
    "every country whose units were merged, matched by name or left with parts outside any unit, was checked against "
    "official national lists by an independent AI agent. The verification sample covers countries whose official lists "
    "could be retrieved. The validation report of the build is published next to the units."
)

NE_ATTRIBUTION = ("Country boundaries, the departments of France and first-level units outside the United States and "
                  "Norway: Natural Earth.")

PUBLISHED_COLUMNS = [
    ("adm0", "unit_id, iso3, level, parent_id, name, unit_type_local, unit_type_en, method, source, source_vintage, license, boundary_vintage, src_ref, adm0_status, ne_type"),
    ("adm1", "unit_id, iso3, level, parent_id, name, unit_type_local, unit_type_en, method, source, source_vintage, license, boundary_vintage, src_ref"),
    ("adm2", "unit_id, iso3, level, parent_id, name, unit_type_local, unit_type_en, method, source, source_vintage, license, boundary_vintage, src_ref"),
    ("disputed_unassigned", "unit_id, label, area_km2, pov"),
    ("contested_areas", "area_id, name, controlled_by, claimed_by, control_since, label, frame_unit_ids, source_control, source_claim, checked_at, checked_by"),
]

# (name, type, nullable, null_meaning, description, unit)
FIELDS = [
    ("unit_id", "string", False, None, "Unit code: ISO3 for countries, ISO3-level-national code below them, for example USA-2-51059.", None),
    ("iso3", "string", False, None, "ISO 3166-1 alpha-3 code of the country.", None),
    ("level", "string", False, None, "Administrative level of the unit: ADM0 (country), ADM1 or ADM2.", None),
    ("parent_id", "string", True, "The unit is a country and has no parent.", "unit_id of the unit one level up.", None),
    ("name", "string", False, None,
     "Name of the unit: for first-level units added in version 0.2.0, the English name of the code in Unicode CLDR where CLDR has one, "
     "otherwise the name in Natural Earth; in France, the name in the official geographic code of INSEE; elsewhere, as given by the "
     "source. For a contested area, its English name.", None),
    ("unit_type_local", "string", True, "No type is given: the source gives none, or the types of this country are not filled in this release.",
     "Type of the unit in the national language. For the United States, France, the United Kingdom and Norway, the type of the unit itself, for example county or commune. For first-level units added in version 0.2.0, the types of first-level units in the country, from the boundary registry: one value if the country has one type, otherwise all types separated by \"/\"; \"|\" separates alternative names of one type.", None),
    ("unit_type_en", "string", True, "No type is given: the source gives none, or the types of this country are not filled in this release.",
     "Type of the unit in English. For the United States, France, the United Kingdom and Norway, the type of the unit itself. For first-level units added in version 0.2.0, the types of first-level units in the country, from the boundary registry: one value if the country has one type, otherwise all types separated by \"/\"; \"|\" separates alternative names of one type.", None),
    ("method", "string", True, "Not applicable to the unit.", "How the unit was made: taken as it is from the source, dissolved from smaller units, or conformed to a national list.", None),
    ("source", "string", False, None, "Publisher or product the unit comes from.", None),
    ("source_vintage", "string", True, "The source gives no edition.", "Edition or date of the source.", None),
    ("license", "string", False, None, "License of the source of the unit.", None),
    ("boundary_vintage", "string", True, "The source gives no edition.", "Date or year of the boundaries.", None),
    ("src_ref", "string", True, "The source gives no reference code.", "Reference of the unit in the source, for example its original code.", None),
    ("adm0_status", "string", True, "Not applicable to the unit.", "Status of the country record, as set by the project's rules for disputed territories.", None),
    ("ne_type", "string", True, "Not applicable to the unit.", "Type of the country record in Natural Earth.", None),
    ("label", "string", True, "Not applicable to the unit.",
     "Label of the area: the name of a disputed or unassigned area; for a contested area, the map caption with the state in control, "
     "the claiming state and the date.", None),
    ("area_km2", "number", True, "Not applicable to the unit.", "Area of the disputed or unassigned area.", "km2"),
    ("pov", "string", True, "Not applicable to the unit.", "Point of view under which the area is drawn.", None),
    ("area_id", "string", False, None, "Code of the contested area, for example CA-0001. It does not change between versions.", None),
    ("frame_unit_ids", "string", False, None, "unit_id of the units of the frame that make up the contested area, separated by semicolons.", None),
    ("controlled_by", "string", False, None, "ISO 3166-1 alpha-3 code of the state in control of the area; several codes are separated by semicolons.", None),
    ("claimed_by", "string", False, None, "ISO 3166-1 alpha-3 code of the state that claims the area; several codes are separated by semicolons.", None),
    ("control_since", "string", False, None, "Year and month, or date, from which the state in control has controlled the area.", None),
    ("source_control", "string", False, None, "Addresses of the documents on the control of the area, separated by semicolons.", None),
    ("source_claim", "string", False, None, "Addresses of the documents on the claim to the area, separated by semicolons.", None),
    ("checked_at", "string", False, None, "Date the sources of the row were checked.", None),
    ("checked_by", "string", False, None, "Who checked the sources: human, script or AI agent with its role (human:…, script:…, agent:…).", None),
]

TILE_FIELDS = [
    ("adm0", "unit_id, name, iso3, level, adm0_status"),
    ("adm1", "unit_id, name, iso3, level"),
    ("adm2", "unit_id, name, iso3, level"),
    ("disputed_unassigned", "unit_id, label"),
    ("contested_areas", "area_id, name, controlled_by, claimed_by, control_since, label"),
]
TILE_ZOOMS = [("adm0", 0), ("adm1", 2), ("adm2", 4), ("disputed_unassigned", 0), ("contested_areas", 0)]

CLDR_SOURCE = '''  - source_id: unicode_cldr
    role: reference
    publisher: "Unicode, Inc."
    product: "Unicode CLDR: subdivision codes and English subdivision names"
    url: "https://github.com/unicode-org/cldr/tree/release-48-2"
    edition: "release-48-2"
    retrieved_at: bnd_meta   # the build takes the download date from the boundaries meta.json
    current_through: null
    bnd_match: ["CLDR"]
    license:
      id: Unicode-3.0
      name: Unicode License v3
      url: "https://github.com/unicode-org/cldr/blob/release-48-2/LICENSE"
      family: attribution
      attribution_text: "First-level unit codes and English names: Unicode CLDR release-48-2, © Unicode, Inc., Unicode License v3."
    rights_basis:
      type: license
      text: "The LICENSE file of the CLDR repository and the SPDX lines of its subdivision files state the Unicode License v3, which requires its copyright and permission notice with copies of the data or in associated documentation."
      checked_at: "2026-10-14"
      checked_by: "script:06_licences.py"
      evidence_url: "https://github.com/unicode-org/cldr/blob/release-48-2/LICENSE"
    publication_mode: open_licence
'''


def q(text: str) -> str:
    """Double-quoted yaml scalar (JSON escaping is valid yaml); non-ASCII kept."""
    return json.dumps(text, ensure_ascii=False)


def folded(prefix: str, text: str, indent: int) -> list[str]:
    pad = " " * indent
    lines = textwrap.wrap(text, width=100 - indent, break_long_words=False, break_on_hyphens=False)
    return [prefix] + [pad + ln for ln in lines]


def block_description() -> list[str]:
    return folded("description: >-", DESCRIPTION, 2)


def block_published_columns() -> list[str]:
    return ["published_columns:"] + [f"  {k}: [{v}]" for k, v in PUBLISHED_COLUMNS]


def block_fields() -> list[str]:
    out = ["fields:"]
    for name, typ, nullable, nullm, desc, unit in FIELDS:
        parts = [f"name: {name}", f"type: {typ}"]
        if unit:
            parts.append(f"unit: {unit}")
        parts.append(f"nullable: {'true' if nullable else 'false'}")
        if nullm:
            parts.append(f"null_meaning: {q(nullm)}")
        parts.append(f"description: {q(desc)}")
        out.append("  - {" + ", ".join(parts) + "}")
    return out


def block_coverage() -> list[str]:
    out = ["coverage:", f"  geography: {q(GEOGRAPHY)}", "  known_gaps:"]
    for gap in KNOWN_GAPS:
        out += folded("    - >-", gap, 6)
    return out


def block_verification() -> list[str]:
    out = ["verification:", "  levels: {source_as_is: 0.0, script_rules: 1.0, human: 0.0}"]
    out += folded("  method: >-", VERIFICATION_METHOD, 4)
    out.append("  sample_share: {}   # the build adds sample_share and levels.agent_sample from the registry")
    return out


def block_display() -> list[str]:
    out = ["display:", "  geometry_type: polygon", '  legend_title: "Administrative boundaries"', "  tile_fields_by_layer:"]
    out += [f"    {k}: [{v}]" for k, v in TILE_FIELDS]
    return out


def block_tiles() -> list[str]:
    out = ["tiles:", "  minzoom: 0", "  maxzoom: 10",
           '  extra_args: ["--detect-shared-borders", "--no-tile-size-limit", "--no-feature-limit"]', "  layers:"]
    out += [f"    {k}: {{minzoom: {z}, maxzoom: 10}}" for k, z in TILE_ZOOMS]
    return out


BLOCKS = {
    "description": block_description,
    "published_columns": block_published_columns,
    "fields": block_fields,
    "coverage": block_coverage,
    "verification": block_verification,
    "display": block_display,
    "tiles": block_tiles,
}

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")


def split_blocks(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    """Top-level blocks: (key, lines). Lines before the first key have key None."""
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for ln in lines:
        m = KEY_RE.match(ln)
        if m:
            blocks.append((m.group(1), [ln]))
        else:
            blocks[-1][1].append(ln)
    return blocks


def trim(block: list[str]) -> tuple[list[str], list[str]]:
    """Content without trailing blank/comment-only lines, and those trailing lines."""
    end = len(block)
    while end > 1 and (not block[end - 1].strip() or block[end - 1].lstrip().startswith("#")) and not block[end - 1].startswith(" "):
        end -= 1
    return block[:end], block[end:]


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    if not YAML_PATH.exists():
        print(f"STOP: {YAML_PATH} not found; run from the repository root")
        return 2
    raw = YAML_PATH.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    trailing_newline = lines and lines[-1] == ""
    if trailing_newline:
        lines = lines[:-1]
    blocks = split_blocks(lines)
    keys = [k for k, _ in blocks]
    for k in BLOCKS:
        if k not in keys:
            print(f"STOP: block {k}: is not in {YAML_PATH}")
            return 2
    changed: list[str] = []
    new_blocks: list[tuple[str | None, list[str]]] = []
    for key, body in blocks:
        if key in BLOCKS:
            content, tail = trim(body)
            new = BLOCKS[key]()
            if content != new:
                changed.append(f"replaced block {key}")
            new_blocks.append((key, new + tail))
        elif key == "sources":
            content, tail = trim(body)
            text = "\n".join(content)
            m = re.search(r'^(\s+attribution_text: )"Country boundaries[^\n]*"\s*$', text, flags=re.M)
            want = f"{m.group(1)}{q(NE_ATTRIBUTION)}" if m else None
            if m and m.group(0).rstrip() != want:
                text = text.replace(m.group(0), want)
                changed.append("set attribution_text of natural_earth")
            elif not m and NE_ATTRIBUTION not in text:
                print("STOP: attribution_text of natural_earth not found")
                return 2
            if "source_id: unicode_cldr" not in text:
                text = text + "\n" + CLDR_SOURCE.rstrip("\n")
                changed.append("added source unicode_cldr")
            new_blocks.append((key, text.split("\n") + tail))
        else:
            new_blocks.append((key, body))
    out_lines = [ln for _, b in new_blocks for ln in b]
    if changed:
        print("Changes:")
        for c in changed:
            print("  -", c)
    else:
        print("Nothing to change: the file is already patched.")
    if apply and changed:
        text = nl.join(out_lines) + (nl if trailing_newline else "")
        YAML_PATH.write_bytes(text.encode("utf-8"))
        print(f"Written {YAML_PATH}")
    elif changed:
        print("Not written (run again with --apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
