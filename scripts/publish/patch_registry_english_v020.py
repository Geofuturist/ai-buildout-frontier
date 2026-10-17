r"""Restore the English text of the 7 old rows of boundaries\boundary_registry.csv (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\patch_registry_english_v020.py            # shows what would change, writes nothing
    python scripts\publish\patch_registry_english_v020.py --apply    # writes the file

Why: the registry in the archive of CODE-BND carried the 7 rows of version 0.1.0 (USA ADM1/ADM2, FRA ADM1/ADM2,
GBR ADM1, NOR ADM1/ADM2) in the old Russian wording, but the published registry has been English since commit 227ce5c
(9 October). The public reference files must have no Cyrillic (gate G7).

Only the cells of these 7 rows that contain Cyrillic are replaced, by the English cells of commit 227ce5c.
The other 104 rows and all other cells are kept byte for byte (line endings too). If another cell of these 7 rows
differs from commit 227ce5c, it is listed and NOT changed.
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

PATH = Path("boundaries") / "boundary_registry.csv"
CYR = re.compile("[\u0400-\u04FF]")
HEADER = ["iso3", "level", "unit_type_local", "unit_type_en", "method", "dissolve_field", "source_name", "source_url", "source_vintage", "license", "attribution", "code_scheme", "expected_units", "verified", "verified_at", "verified_by", "verified_against", "notes"]
ENGLISH = {
 "USA|ADM1": {
  "iso3": "USA",
  "level": "ADM1",
  "unit_type_local": "state",
  "unit_type_en": "state",
  "method": "national_conformed",
  "dissolve_field": "",
  "source_name": "Census cb_2023_us_state_500k",
  "source_url": "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip",
  "source_vintage": "2023",
  "license": "U.S. Government Work",
  "attribution": "U.S. Census Bureau",
  "code_scheme": "STATEFP",
  "expected_units": "51",
  "verified": "true",
  "verified_at": "2026-09-28",
  "verified_by": "script:validate_boundaries.py",
  "verified_against": "US Census Bureau cartographic boundary files 2023 (source of the geometry itself): 50 states and DC, 51 units",
  "notes": ""
 },
 "USA|ADM2": {
  "iso3": "USA",
  "level": "ADM2",
  "unit_type_local": "county",
  "unit_type_en": "county-equivalent",
  "method": "national_conformed",
  "dissolve_field": "",
  "source_name": "Census cb_2023_us_county_500k",
  "source_url": "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip",
  "source_vintage": "2023",
  "license": "U.S. Government Work",
  "attribution": "U.S. Census Bureau",
  "code_scheme": "GEOID (FIPS)",
  "expected_units": "3144",
  "verified": "true",
  "verified_at": "2026-09-28",
  "verified_by": "script:validate_boundaries.py",
  "verified_against": "US Census Bureau cartographic boundary files 2023 (source of the geometry itself): 3144 counties and equivalents, incl. 9 Connecticut planning regions",
  "notes": "expected_units fixed at pre-flight: territories (STATEFP 60, 66, 69, 72, 78) excluded"
 },
 "FRA|ADM1": {
  "iso3": "FRA",
  "level": "ADM1",
  "unit_type_local": "région",
  "unit_type_en": "region",
  "method": "ne_dissolve",
  "dissolve_field": "region",
  "source_name": "Natural Earth 5.1.2",
  "source_url": "https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2",
  "source_vintage": "v5.1.2",
  "license": "public domain",
  "attribution": "Not required (public domain); optional credit: Made with Natural Earth",
  "code_scheme": "INSEE région",
  "expected_units": "18",
  "verified": "true",
  "verified_at": "2026-10-09",
  "verified_by": "human:V",
  "verified_against": "INSEE Code officiel géographique (https://www.insee.fr/fr/information/2560452): 18 regions",
  "notes": "Unit count checked by V. Earlier entry of 2026-09-26 (set in the boundaries specification) replaced on 2026-10-09"
 },
 "FRA|ADM2": {
  "iso3": "FRA",
  "level": "ADM2",
  "unit_type_local": "département",
  "unit_type_en": "department",
  "method": "ne_as_is",
  "dissolve_field": "",
  "source_name": "Natural Earth 5.1.2",
  "source_url": "https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2",
  "source_vintage": "v5.1.2",
  "license": "public domain",
  "attribution": "Not required (public domain); optional credit: Made with Natural Earth",
  "code_scheme": "INSEE département",
  "expected_units": "101",
  "verified": "true",
  "verified_at": "2026-10-09",
  "verified_by": "human:V",
  "verified_against": "INSEE Code officiel géographique (https://www.insee.fr/fr/information/2560452): 101 departments",
  "notes": "Unit count checked by V. Earlier entry of 2026-09-26 (set in the boundaries specification) replaced on 2026-10-09"
 },
 "GBR|ADM1": {
  "iso3": "GBR",
  "level": "ADM1",
  "unit_type_local": "country",
  "unit_type_en": "constituent country",
  "method": "ne_dissolve",
  "dissolve_field": "gu_a3",
  "source_name": "Natural Earth 5.1.2",
  "source_url": "https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2",
  "source_vintage": "v5.1.2",
  "license": "public domain",
  "attribution": "Not required (public domain); optional credit: Made with Natural Earth",
  "code_scheme": "ENG/SCT/WLS/NIR",
  "expected_units": "4",
  "verified": "true",
  "verified_at": "2026-10-09",
  "verified_by": "human:V",
  "verified_against": "ONS Administrative geography (https://www.ons.gov.uk/methodology/geography/ukgeographies/administrativegeography): 4 countries (England, Scotland, Wales, Northern Ireland)",
  "notes": "No GBR ADM2 in v0.1: local government reorganisations of 2019-2023 are not reflected in Natural Earth. Unit count checked by V. Earlier entry of 2026-09-26 (set in the boundaries specification) replaced on 2026-10-09"
 },
 "NOR|ADM1": {
  "iso3": "NOR",
  "level": "ADM1",
  "unit_type_local": "fylke",
  "unit_type_en": "county",
  "method": "national_conformed",
  "dissolve_field": "",
  "source_name": "Kartverket, Administrative enheter fylker (Inndelingsbase) + Natural Earth (Svalbard)",
  "source_url": "https://data.norge.no/nb/datasets/cffde12f-3530-4406-9aa0-d6d4519ef077/administrative-enheter-fylker",
  "source_vintage": "2026-01-01",
  "license": "CC BY 4.0",
  "attribution": "© Kartverket, CC BY 4.0",
  "code_scheme": "fylkesnummer; Svalbard: 21",
  "expected_units": "16",
  "verified": "true",
  "verified_at": "2026-09-28",
  "verified_by": "script:validate_boundaries.py",
  "verified_against": "Kartverket Inndelingsbase, reference date 2026-01-01 (source of the geometry itself): 15 counties; Svalbard added from Natural Earth",
  "notes": "ADM1 = 15 Kartverket counties (fylker) + Svalbard from Natural Earth as is (territory outside the counties, no ADM2). Jan Mayen and Bouvet Island are not administrative units: they get no ADM1 and stay part of Norway ADM0 (project decision, 2026-09-27). Kartverket Inndelingsbase includes sea areas: display files are clipped to the Natural Earth coastline, analysis files keep the full extent"
 },
 "NOR|ADM2": {
  "iso3": "NOR",
  "level": "ADM2",
  "unit_type_local": "kommune",
  "unit_type_en": "municipality",
  "method": "national_conformed",
  "dissolve_field": "",
  "source_name": "Kartverket, Administrative enheter kommuner (Inndelingsbase)",
  "source_url": "https://data.norge.no/en/datasets/3557d23d-8188-4136-b227-c854f89a6e8e/administrative-enheter-kommuner",
  "source_vintage": "2026-01-01",
  "license": "CC BY 4.0",
  "attribution": "© Kartverket, CC BY 4.0",
  "code_scheme": "kommunenummer",
  "expected_units": "357",
  "verified": "true",
  "verified_at": "2026-09-28",
  "verified_by": "script:validate_boundaries.py",
  "verified_against": "Kartverket Inndelingsbase, reference date 2026-01-01 (source of the geometry itself): 357 municipalities",
  "notes": "Kartverket Inndelingsbase includes sea areas: display files are clipped to the Natural Earth coastline, analysis files keep the full extent"
 }
}


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    if not PATH.exists():
        print(f"STOP: {PATH} not found; run from the repository root")
        return 2
    raw = PATH.read_bytes().decode("utf-8")
    bom = raw.startswith("\ufeff")
    text = raw[1:] if bom else raw
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    consumed: list[str] = []

    def feed():
        for ln in lines:
            consumed.append(ln)
            yield ln

    reader = csv.reader(feed())
    records: list[tuple[str, list[str]]] = []
    for row in reader:
        records.append(("".join(consumed), row))
        consumed.clear()
    if not records or records[0][1] != HEADER:
        print("STOP: the header of the registry is not the expected one:", records[0][1] if records else None)
        return 2
    out: list[str] = [records[0][0]]
    changed = 0
    for raw_rec, row in records[1:]:
        key = f"{row[0]}|{row[1]}"
        if key not in ENGLISH or not any(CYR.search(c) for c in row):
            out.append(raw_rec)
            continue
        eng = ENGLISH[key]
        new = list(row)
        for i, col in enumerate(HEADER):
            if CYR.search(row[i]):
                new[i] = eng[col]
                changed += 1
                print(f"  {key} column {col}:\n    was: {row[i][:110]}\n    now: {eng[col][:110]}")
            elif row[i] != eng[col]:
                print(f"  {key} column {col}: differs from commit 227ce5c, NOT changed: {row[i][:60]!r} vs {eng[col][:60]!r}")
        buf = io.StringIO()
        csv.writer(buf, lineterminator=raw_rec[len(raw_rec.rstrip("\r\n")):] or nl).writerow(new)
        out.append(buf.getvalue())
    if not changed:
        print("Nothing to change: no Cyrillic in the old rows.")
        return 0
    result = ("\ufeff" if bom else "") + "".join(out)
    left = [c for c in re.findall(r"[\u0400-\u04FF]+", result)]
    print(f"{changed} cell(s) replaced; Cyrillic left in the file: {len(left)}")
    if apply:
        PATH.write_bytes(result.encode("utf-8"))
        print(f"Written {PATH}")
    else:
        print("Not written (run again with --apply).")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
