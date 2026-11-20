r"""Patch content\methodology.md for abf-boundaries v0.3.0 (idempotent). Texts: RES_texts_BND_v0_3_0.md r1, section 7.

Run command (from the repository root, Windows):
    python scripts\publish\patch_methodology_bnd_v030.py             # shows what would change, writes nothing
    python scripts\publish\patch_methodology_bnd_v030.py --apply     # writes the file

Replaces the whole section "Administrative boundaries · ADM0, ADM1, ADM2" and the bullet "Boundaries" of "Known limitations".
The section is made from the text of version 0.2.0 (patch_methodology_bnd_v020.py, which must be in the same folder) with the
edits of RES section 7.1; the rest of the file is kept byte for byte, line endings too.
The sentence "The build was reproduced on a second machine." is NOT in the new section: it was true for 0.2.0 (all 5 511 rows
of unit_hashes.csv equal in two environments); nobody has repeated it for 0.3.0. Option --with-reproduced puts it back.
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_methodology_bnd_v020 as m20  # noqa: E402

PATH = m20.PATH
HEADING = m20.HEADING
REPRODUCED = m20.REPRODUCED


def bullet(text: str) -> str:
    lines = textwrap.wrap(text, width=100, initial_indent="- ", subsequent_indent="  ",
                          break_long_words=False, break_on_hyphens=False)
    return "\n".join(lines) + "\n"


def wrap_tail(text: str) -> str:
    """Continuation of a bullet: wrapped lines with the two-space indent."""
    return "\n".join(textwrap.wrap(text, width=100, initial_indent="  ", subsequent_indent="  ",
                                   break_long_words=False, break_on_hyphens=False)) + "\n"


TABLE_ROWS = """  | Colombia | 33: 32 departments and the Capital District of Bogotá | — | DANE, Marco Geoestadístico Nacional |
  | Estonia | 15 counties | — | Maa- ja Ruumiamet |
  | Hong Kong | 18 districts | — | Home Affairs Department, via DATA.GOV.HK |
  | Indonesia | 38 provinces | — | Badan Informasi Geospasial, regencies and cities merged into provinces |
  | Ireland | 26 counties | — | Tailte Éireann, CC BY 4.0 |
  | Latvia | 42: 35 municipalities and 7 state cities | — | State Land Service, CC BY 4.0 |
  | Luxembourg | 12 cantons | — | Administration du cadastre et de la topographie, CC0 |
  | Mexico | 32: 31 states and Mexico City | — | INEGI, via OCHA (HDX), CC BY 3.0 IGO |
  | New Zealand | 17: 16 regions and the Chatham Islands Territory | — | Stats NZ, CC BY 4.0 |
  | Peru | 25: 24 departments and Callao | — | Instituto Geográfico Nacional, ODC-By |
  | Philippines | 18 regions | — | provinces via OCHA (HDX), CC BY 3.0 IGO, grouped by law |
  | South Korea | 16 provinces and metropolitan cities | — | Statistics Korea (SGIS) |
  | Taiwan | 22: 6 special municipalities, 13 counties, 3 cities | — | Ministry of the Interior (NLSC), villages merged, OGDL 1.0 |
  | Thailand | 77: 76 provinces and Bangkok | — | via OCHA (HDX), CC BY 3.0 IGO |
  | Vietnam | 34 provinces and cities | — | via OCHA (HDX), CC BY 3.0 IGO |
"""

NEW_BULLETS = "".join(bullet(t) for t in [
    "**National first levels for 15 countries.** Where Natural Earth and CLDR do not match the official list, or a reform "
    "is not reflected, the first level comes from a national source with an open license: the publisher's own file where "
    "it could be downloaded, otherwise OCHA's copy on the Humanitarian Data Exchange that names the national source. Each "
    "country passed four gates before its units were published: a license statement found by script on the publisher's "
    "page, the file with its SHA-256, the number of units equal to an official list or legal act, and unambiguous codes.",
    "**Units defined by law.** Where a law has changed the first level and no file shows it yet, the project assembles the "
    "new unit from whole units of the source, along their own boundaries, and records the law. South Korea: "
    "Jeonnam-Gwangju Integrated Special City, created on July 1, 2026 by Act No. 21446, is the union of the former South "
    "Jeolla Province and Gwangju Metropolitan City. The Philippines: the Negros Island Region is Negros Occidental with "
    "Bacolod City, Negros Oriental and Siquijor (Republic Act No. 12000, Sec. 3); Sulu is assigned to Zamboanga Peninsula "
    "under Executive Order No. 91 of July 30, 2025.",
    "**Indonesia.** The provinces are merged from BIG's regencies and cities. The map service of the source generalized "
    "each regency separately, so neighbors did not share one line; overlaps between provinces were removed, and narrow "
    "gaps remain, listed in the known limitations. Coordinates are rounded to four decimal places, following BIG's "
    "regulation on sharing geospatial data abroad.",
    "**Coastlines.** National first levels keep their own coastline, even where it lies outside the country outline of the "
    "frame; nothing is cut at sea, except in Hong Kong, whose districts include sea areas and are shown cut to the "
    "coastline of the frame. Islands that other states also claim are shown as each national file draws them; the project "
    "takes no position on sovereignty.",
])

OUT_OF_DATE_OLD = "- **What may be out of date.**"
OUT_OF_DATE = bullet(
    "**What may be out of date.** For the 104 countries added in version 0.2.0, ADM1 follows the top level of ISO 3166-2 "
    "as recorded in Unicode CLDR release-48-2; reforms after that release may not be reflected. National first levels are "
    "as of the dates of their files. Algeria, Burkina Faso, Mali and Burundi reorganized their first level, and no open "
    "boundaries of the new division were found: they show national borders only, like the other 115 countries and "
    "territories without a checked first level. An outdated division on a site about checkable data would be worse than "
    "none.")

FITTING = bullet(
    "**Fitting national data to the frame.** National boundaries are fitted to the frame along land borders with "
    "neighbors only, within about 11 km of the border. The coastline stays national.")

TWO_GEOMETRIES = bullet(
    "**Two geometries.** Calculations use the official boundaries at full resolution: for the United States, the Census "
    "1:500,000 files; for Norway and the 15 countries with national first levels, the national files, published as "
    "analysis files. The map shows a version simplified with a tolerance of 0.0005 degrees, about 50 m; no unit changes "
    "its area by more than 2%. Indonesia is not simplified further: the source is already generalized. Both geometries "
    "carry the same unit codes, so what you see is what we counted on. The subdivisions of the other countries come from "
    "Natural Earth and are generalized: they are not the official national boundaries.")

CODES_TAIL = wrap_tail(
    "For the 15 countries with national first levels, the national code is the code of the source (`PHL-1-18` is the "
    "Negros Island Region, `TWN-1-64000` is Kaohsiung), or the ISO 3166-2 code for Luxembourg and Ireland. A unit "
    "assembled by the project carries a code made of the source codes it joins: `KOR-1-X2436`.")

CHECKS_TAIL = wrap_tail(
    "Between national first levels and their neighbors, overlaps above 0.05 km² stop the build; for Indonesia, whose "
    "coordinates are rounded, the limit is 1 km² per pair and 5 km² for the country. Two overlaps between islands claimed "
    "by more than one state are listed with the reason and allowed. All units of the previous version are compared with "
    "it by hash.")

LICENSE = bullet(
    "**License.** CC BY 4.0 for the boundary set. Each unit carries its own source and license: Natural Earth (public "
    "domain), the U.S. Census Bureau (public domain), Kartverket, Stats NZ, Tailte Éireann and the State Land Service of "
    "Latvia (CC BY 4.0), Luxembourg (CC0), Peru (ODC-By), Taiwan (Open Government Data License 1.0), OCHA's copies (CC BY "
    "3.0 IGO), and the terms of DANE, DATA.GOV.HK and data.go.kr; the boundaries of Indonesia are published by BIG without "
    "license terms and are included on the basis of Indonesian copyright law. Codes and English names of the first level "
    "come from Unicode CLDR (© Unicode, Inc., Unicode License v3).")

BULLET = bullet(
    "**Boundaries** outside the United States, Norway and 15 countries with national sources are generalized at 1:10 "
    "million; first levels of 104 countries follow CLDR release-48-2, which may miss later reforms. 119 countries and "
    "territories have national borders only. National files keep their own coastlines and the islands they claim. In "
    "Indonesia, narrow gaps remain between provinces. Crimea and Sevastopol are shown under Russia, the state in "
    "control, by a stated rule; Ukraine's claim is in the layer contested_areas.")


def _bullet_span(text: str, start_marker: str) -> tuple[int, int]:
    """Span of a top-level bullet of the section: from its marker to the next `\\n- **` or the section end."""
    i = text.index(start_marker)
    m = re.compile(r"\n(?=- \*\*|\Z)").search(text, i + 1)
    j = (m.end() if m else len(text))
    return i, j


def make_section(reproduced: bool) -> str:
    s = m20.SECTION.replace("{reproduced}", "")
    # 1. table rows
    row = "  | 104 more countries | 1,578 units: the top level of ISO 3166-2 | — | Natural Earth, as is or merged; codes and names from Unicode CLDR |\n"
    assert row in s
    s = s.replace(row, row + TABLE_ROWS)
    # 2. new bullets after "How the first level was checked"
    i, j = _bullet_span(s, "- **How the first level was checked.**")
    s = s[:j] + NEW_BULLETS + s[j:]
    # 3. what may be out of date
    i, j = _bullet_span(s, OUT_OF_DATE_OLD)
    s = s[:i] + OUT_OF_DATE + s[j:]
    # 4. fitting national data
    i, j = _bullet_span(s, "- **Fitting national data to the frame.**")
    s = s[:i] + FITTING + s[j:]
    # 5. two geometries
    i, j = _bullet_span(s, "- **Two geometries.**")
    s = s[:i] + TWO_GEOMETRIES + s[j:]
    # 6. unit codes: sentences appended
    i, j = _bullet_span(s, "- **Unit codes.**")
    assert s[i:j].endswith("\n")
    s = s[:j] + CODES_TAIL + s[j:]
    # 7. checks: sentences appended (the sentence about the second machine only with --with-reproduced)
    i, j = _bullet_span(s, "- **Checks run at every build.**")
    tail = (REPRODUCED.strip() + " ") if reproduced else ""
    s = s[:j] + CHECKS_TAIL + (wrap_tail(tail.strip()) if tail else "") + s[j:]
    # 8. license
    i, j = _bullet_span(s, "- **License.**")
    s = s[:i] + LICENSE + "\n" + s[j:]   # the section ends with a blank line
    return s


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    reproduced = "--with-reproduced" in argv
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
    new_section = make_section(reproduced)
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
    print("The sentence about the second machine is " + ("included." if reproduced else "NOT included."))
    if apply:
        PATH.write_bytes(text.replace("\n", nl).encode("utf-8"))
        print(f"Written {PATH}")
    else:
        print("Not written (run again with --apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
