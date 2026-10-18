r"""Patch content\methodology.md for abf-boundaries v0.2.0 (idempotent). Texts: RES_texts_BND_v0_2_0.md section 4 (r5, 18 October: Crimea and Sevastopol under Russia).

Run command (from the repository root, Windows):
    python scripts\publish\patch_methodology_bnd_v020.py                 # shows what would change, writes nothing
    python scripts\publish\patch_methodology_bnd_v020.py --apply         # writes the file
    python scripts\publish\patch_methodology_bnd_v020.py --apply
        # includes the sentence "The build was reproduced on a second machine." (CODE-BND confirmed on 17 October:
        # all 5 511 rows of unit_hashes.csv are equal in two environments). Option --without-reproduced leaves it out.

Replaces the whole section "Administrative boundaries · ADM0, ADM1, ADM2" and the bullet "Boundaries" of "Known limitations".
The rest of the file is kept byte for byte, line endings too.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATH = Path("content") / "methodology.md"
HEADING = "## Administrative boundaries · ADM0, ADM1, ADM2"
REPRODUCED = " The build was reproduced on a second machine."

SECTION = '''## Administrative boundaries · ADM0, ADM1, ADM2

- **One frame for the whole world.** Natural Earth at 1:10 million, version 5.1.2. Where borders are
  disputed, we use the U.S. government's point of view, because the main sources in this project are
  U.S. federal, with one exception described next. **The boundaries do not express a position of the
  project.** Five disputed areas belong to no country in this view: Abyei, the Ilemi Triangle, the
  Siachen Glacier, the Southern Patagonian Ice Field and Rincón de Artigas. They are drawn with a
  neutral fill, not left blank like the sea.
- **Whole units under another state's control are shown under that state.** Where sources show that
  another recognized state controls whole units of the frame and has made them part of its own
  administrative division, the map shows the state in control and records the other state's claim.
  In this release this applies to Crimea and Sevastopol: under Russian control since 2014 and listed
  among the subjects of the Russian Federation in its Constitution; Ukraine's claim is recorded with
  sources. Areas of the Donetsk, Luhansk, Zaporizhzhia and Kherson regions under Russian control
  since 2022 remain under Ukraine: the rule applies only to whole units, and we found no open dated
  line of control.
- **Areas of disputed control are a separate layer.** The layer contested_areas lists, for each
  area, the state in control, the state that claims it, the date from which control is counted, and
  the documents for both. This release lists two areas: Crimea and Sevastopol.
- **Levels follow each country's own structure**, not whatever a source calls “admin-1”. This
  release:

  | Country | First level | Second level | Source |
  |---|---|---|---|
  | World | 242 countries and territories | — | Natural Earth |
  | United States | 51 (states and the District of Columbia) | 3,144 counties and county-equivalents | U.S. Census Bureau cartographic boundaries 1:500,000, 2023 |
  | France | 18 regions | 101 departments | Natural Earth, merged |
  | United Kingdom | 4 countries | — | Natural Earth, merged |
  | Norway | 15 counties and Svalbard | 357 municipalities | Kartverket, CC BY 4.0, reference date 1 January 2026 |
  | 104 more countries | 1,578 units: the top level of ISO 3166-2 | — | Natural Earth, as is or merged; codes and names from Unicode CLDR |

- **The first level of the 104 countries** is the top level of ISO 3166-2, the international
  standard for subdivision codes, as recorded in Unicode CLDR release-48-2. Natural Earth units are
  taken as they are or merged, and only where they match that list code for code. A few written
  corrections apply: subtypes of one level count as one level, such as states and a federal
  district; codes of territories that our frame shows as separate countries are left out; where the
  top level is not administrative, the next one is used, case by case with an official document
  (Guinea-Bissau in this release); small parts of a country that have no code in the list stay in
  the country without a first-level unit, up to 1% of its area; a country where five or more units
  lie inside other units, such as cities inside counties, is held back for review. Names are the
  English names of the codes in CLDR.
- **How the first level was checked.** For every country, a script matched the units to the CLDR
  code list. A random sample of countries, and every country whose units were merged, matched by
  name or left with parts outside any unit, was checked against official national lists by an
  independent AI agent. The verification sample covers countries whose official lists could be
  retrieved. Each country's entry in the boundary registry
  (https://github.com/Geofuturist/ai-buildout-frontier/blob/main/boundaries/boundary_registry.csv)
  records its method, its expected number of units and what it was checked against.
- **What may be out of date.** ADM1 follows the top level of ISO 3166-2 as recorded in Unicode CLDR
  release-48-2; reforms after that release may not be reflected. The other 134 countries and
  territories show national borders only, until we check their subdivisions against an official
  list. Burkina Faso and Vietnam are among them: both reorganized their first level in 2025, and the
  reference does not reflect it. An outdated division on a site about checkable data would be worse
  than none.
- **Fitting national data to the frame.** National boundaries of the United States and Norway are
  fitted to the frame along land borders with neighbors only. The coastline stays national.
- **Two geometries.** Calculations use the official boundaries at full resolution: for the United
  States, the Census 1:500,000 files. The map shows a simplified version. Both carry the same unit
  codes, so what you see is what we counted on. The subdivisions of all other countries come from
  Natural Earth and are generalized: they are not the official national boundaries.
- **Cut to the country.** First-level units are cut to the outline of their country. Where Natural
  Earth draws a unit beyond that outline, the part outside is left out and listed in the validation
  report; the largest is 2,268 km² of Ladakh (IND-1-LA) inside the outline of China in this point of
  view.
- **Unit codes.** Countries: ISO 3166 three-letter codes (`USA`). Subdivisions:
  `{country}-{level}-{national code}`, for example `USA-1-51` (Virginia) or `USA-2-51059` (Fairfax
  County). For the 104 countries added in version 0.2.0, the national code is the ISO 3166-2 code:
  `POL-1-24` is Silesia. France keeps its INSEE codes (`FRA-1-84`). Crimea and Sevastopol, shown
  under Russia, carry codes of Russia's OKATO classifier (`RUS-1-35`, `RUS-1-67`), because ISO
  3166-2 lists them under Ukraine.
- **Checks run at every build.** No overlaps between units. No gaps except a reviewed list of seas,
  disputed areas and slivers. No land outside every country: the country layer is compared with the
  land of the Natural Earth admin-1 file, and an uncovered area of 100 km² or more stops the build.
  We added this check after version 0.1.0 left Adjara, part of Georgia, outside every country;
  version 0.2.0 corrects it. Every unit inside its parent. Unit counts as expected. Subdivisions
  are published only for countries whose entry in the boundary registry has been verified.{reproduced}
- **License.** CC BY 4.0 for the boundary set. Each unit carries its own source and license. Codes
  and English names of the first level come from Unicode CLDR (© Unicode, Inc., Unicode License v3).

'''

BULLET = '''- **Boundaries** outside the United States and Norway are generalized at 1:10 million. First levels
  of 104 countries follow CLDR release-48-2 and may miss later reforms; 134 countries and
  territories have national borders only. Crimea and Sevastopol are shown under Russia, the state in
  control, by a stated rule; Ukraine's claim is in the layer contested_areas.
'''


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    reproduced = "--without-reproduced" not in argv
    if not PATH.exists():
        print(f"STOP: {PATH} not found; run from the repository root")
        return 2
    raw = PATH.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    changed: list[str] = []

    m = re.search(rf"^{re.escape(HEADING)}\n.*?(?=^## )", text, flags=re.S | re.M)
    if not m:
        print(f"STOP: section {HEADING!r} not found")
        return 2
    new_section = SECTION.replace("{reproduced}", REPRODUCED if reproduced else "")
    if m.group(0) != new_section:
        text = text[:m.start()] + new_section + text[m.end():]
        changed.append("replaced section Administrative boundaries")

    m = re.search(r"^- \*\*Boundaries\*\*.*?(?=^- \*\*|^\n|^## )", text, flags=re.S | re.M)
    if not m:
        print("STOP: bullet '- **Boundaries**' of Known limitations not found")
        return 2
    if m.group(0) != BULLET:
        text = text[:m.start()] + BULLET + text[m.end():]
        changed.append("replaced bullet Boundaries of Known limitations")

    if not changed:
        print("Nothing to change: the file is already patched.")
        return 0
    print("Changes:")
    for c in changed:
        print("  -", c)
    print("The sentence about the second machine is " + ("included." if reproduced else "NOT included (--without-reproduced)."))
    if apply:
        PATH.write_bytes(text.replace("\n", nl).encode("utf-8"))
        print(f"Written {PATH}")
    else:
        print("Not written (run again with --apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
