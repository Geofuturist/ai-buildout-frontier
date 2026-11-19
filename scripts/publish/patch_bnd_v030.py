r"""Patch layers\abf_boundaries.yaml for the release abf-boundaries v0.3.0 (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\patch_bnd_v030.py            # shows what would change, writes nothing
    python scripts\publish\patch_bnd_v030.py --apply    # writes the file

Texts: RES_texts_BND_v0_3_0.md r1 (19 November), sections 1-6, with the decisions of ARCH7 of 19 November (SPEC_BND r13 3l).
What it does:
  - replaces the top-level blocks description, fields, coverage, verification (published_columns, display and tiles are
    taken over from patch_bnd_v020.py: they do not change);
  - sets the attribution text of the source natural_earth;
  - adds the 15 national sources at the end of `sources` (each only if its source_id is not there yet).
Everything else is kept byte for byte, line endings too. The shares of verification (sample_share, agent_sample) are NOT
written here: the build computes them from the registry.
Needs patch_bnd_v020.py in the same folder (it is in the repository).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_bnd_v020 as p20  # noqa: E402

YAML_PATH = p20.YAML_PATH
q = p20.q
folded = p20.folded

N_MULTI = 32   # countries with more than one type ("/" in the registry), 119 countries outside USA, FRA, GBR, NOR
N_EMPTY = 21   # countries with no type filled

DESCRIPTION = (
    "Administrative units of the world: countries (ADM0) everywhere, first-level units (ADM1) for 123 countries and "
    "second-level units (ADM2) for the United States, France and Norway, in the countries whose entry in the boundary "
    "registry has been verified. Every unit has a code unit_id: ISO3 for countries, ISO3-level-national code below them "
    "(for example USA-2-51059, POL-1-24 or PHL-1-18). Units carry the geometry used on the map; for the United States, "
    "Norway and the 15 countries with national first-level boundaries, the national geometry used for calculations is "
    "published in separate analysis files. Boundaries follow the U.S. government's point of view, with one rule-based "
    "exception, and do not express a position of the project. The exception: where sources show that another recognized "
    "state controls whole units of the frame and has made them part of its own administrative division, the frame shows "
    "the state in control. In this release this applies to Crimea and Sevastopol, shown under Russia. The contested_areas "
    "layer lists areas of disputed control: the state in control, the state that claims the area, the date from which "
    "control is counted, and the sources for both. Areas that the U.S. point of view assigns to no country are a separate "
    "layer. Changes from 0.2.0: first-level units from national sources for 15 countries (425 units): Colombia, Estonia, "
    "Hong Kong, Indonesia, Ireland, Latvia, Luxembourg, Mexico, New Zealand, Peru, the Philippines, South Korea, Taiwan, "
    "Thailand and Vietnam; Svalbard added to the analysis file of Norway; all units of version 0.2.0 unchanged."
)

GEOGRAPHY = ("World (ADM0); ADM1 for 123 countries and ADM2 for the United States, France and Norway, the countries "
             "with a verified entry in the boundary registry")

NE_ATTRIBUTION = ("Country boundaries, the departments of France and first-level units of the countries without a "
                  "national source: Natural Earth.")

_G = p20.KNOWN_GAPS   # items of 0.2.0: 0 and 1 stay, 3 changes its first words, 6-9 stay
KNOWN_GAPS = [
    _G[0],
    _G[1],
    ("For the 104 countries added in version 0.2.0, ADM1 follows the top level of ISO 3166-2 as recorded in Unicode CLDR "
     "release-48-2; reforms after that release may not be reflected. Algeria (69 wilayas, Law No. 26-06 of 2026), Burkina "
     "Faso (17 regions, decided by the Council of Ministers on July 2, 2025), Mali (19 regions and the District of "
     "Bamako, Law No. 2023-006) and Burundi (5 provinces, Organic Law No. 1/05 of March 16, 2023) have reorganized their "
     "first level; no open boundaries of the new division were found, so these countries have ADM0 only."),
    "First-level units built from Natural Earth are cut to the outline of their country. "
    + _G[3].split("First-level units are cut to the outline of their country. ", 1)[1],
    ("ADM1 units exist only for countries whose registry entry has been verified (123 in this release); ADM2 units exist "
     "for the United States, France and Norway. The other 119 countries and territories have ADM0 only."),
    ("First-level units outside the United States, Norway and the 15 countries added in version 0.3.0, and the "
     "departments of France, are built from Natural Earth 1:10m units. They are generalized and are not the official "
     "national boundaries."),
    _G[6],
    _G[7],
    _G[8],
    _G[9],
    ("For first-level units added in versions 0.2.0 and 0.3.0, unit_type_local and unit_type_en give the types of "
     f"first-level units in the country, not the type of each unit. In {N_MULTI} countries with more than one type, such "
     "as municipalities and state cities, all types are listed, separated by \"/\". In "
     f"{N_EMPTY} countries the types are not filled in this release. The type of each unit is planned for a later version."),
    ("First-level units from national sources keep the national coastline. Where it lies outside the country outline of "
     "the frame, the parts outside, mostly coastal waters, lagoons and small islands that Natural Earth does not draw, "
     "are not cut: from about 70 km² in Latvia to about 32,300 km² in Indonesia, at most 3.4% of a country's area (South "
     "Korea). In Hong Kong, whose districts include sea areas, the map shows the districts cut to the coastline of the "
     "frame (1,036 km² of 2,755 km²); the analysis file keeps the official districts."),
    ("National files include islands that other states also claim or control. Each file is shown as published; the "
     "project takes no position on sovereignty. Khanh Hoa (VNM-1-56) includes the Spratly Islands (Truong Sa) and Da Nang "
     "(VNM-1-48) the Paracel Islands (Hoang Sa), as drawn in the Vietnamese file: about 3,367 km² and 715 km² of these "
     "units, mostly sea and reefs, lie outside the Vietnam outline of this frame. Mimaropa (PHL-1-17) includes the "
     "Kalayaan Island Group in the Spratly Islands; about 166 km² of it lies outside the Philippines outline. Kaohsiung "
     "(TWN-1-64000) includes Taiping (Itu Aba) Island. Around Taiping and Thitu (Pag-asa) islands, Khanh Hoa overlaps "
     "Kaohsiung by about 0.44 km² and Mimaropa by about 0.40 km². Yilan (TWN-1-10002) includes the Diaoyutai Islands, "
     "about 5.6 km², which the frame shows as part of Japan (the Senkaku Islands, administered by Japan); the People's "
     "Republic of China also claims them. North Gyeongsang (KOR-1-37) includes Dokdo, about 0.16 km² outside any country "
     "in this frame; Japan also claims the islets as Takeshima."),
    ("Indonesia: province boundaries come from BIG's map service, which generalized each regency and city "
     "(kabupaten/kota) separately. Overlaps between provinces were removed; narrow gaps along internal borders remain, "
     "each smaller than 1 km². Together with lakes cut out in the source file, gaps inside Indonesia total about 3.90 km² "
     "in 3,124 pieces. A point in such a gap falls in no province. Along the borders with Malaysia and Timor-Leste, "
     "Indonesian provinces overlap neighboring units by up to about 0.9 km² per pair, about 2.2 km² in total. A cleaner "
     "geometry is planned for the next version."),
    ("Indonesia: coordinates are rounded to four decimal places (about 11 m), following BIG Regulation No. 1 of 2026 on "
     "sharing geospatial data abroad. BIG notes that boundaries with indicative status are not a legal reference."),
    ("Peru: the Instituto Geográfico Nacional publishes the departmental boundaries as reference boundaries "
     "(\"límites referenciales\")."),
    ("Mexico, the Philippines, Thailand and Vietnam come from OCHA's copies of national boundaries on the Humanitarian "
     "Data Exchange, not from the national publishers; we could not compare the copies with the national files. Their "
     "dates are those of the HDX datasets, not of the national sources: Mexico 2021-06-18, Thailand 2022-01-22, the "
     "Philippines 2025-02-13, Vietnam 2025-09-25. The regions of the Philippines are assembled from OCHA's provinces "
     "under current law (see the methodology)."),
    ("New Zealand: small islands that belong to no regional council, apart from the Chatham Islands Territory, are not "
     "part of any first-level unit."),
    ("South Korea: Jeonnam-Gwangju Integrated Special City (KOR-1-X2436), created on July 1, 2026, has no ISO 3166-2 code "
     "yet; its English name is the project's translation. Its boundary is the union of the former South Jeolla Province "
     "and Gwangju Metropolitan City in the 2025 file of Statistics Korea."),
    ("Dates of the national files: where the source gives no edition date, the date is the day the file was retrieved "
     "(Peru 2026-11-09, Hong Kong 2026-11-15)."),
]
assert len(KNOWN_GAPS) == 20

VERIFICATION_METHOD = (
    "Units are built by script from the sources by the method named in the registry; the registry marks a country and "
    "level as verified before its units are published. For the first-level units added in version 0.2.0, the code list "
    "of each country was matched to Unicode CLDR release-48-2 by script, and a random sample of countries, together with "
    "every country whose units were merged, matched by name or left with parts outside any unit, was checked against "
    "official national lists by an independent AI agent. The verification sample covers countries whose official lists "
    "could be retrieved. For the 15 countries added in version 0.3.0, a script found the license statement on the "
    "publisher's saved page, recorded the SHA-256 of each file, and compared the number of units with an official list "
    "or legal act; units assembled under a law were checked with control points. Every build compares all units with "
    "the previous version by hash. The validation report of the build is published next to the units."
)

NAME_DESCRIPTION = (
    "Name of the unit. For first-level units added in versions 0.2.0 and 0.3.0, the English name of the code in Unicode "
    "CLDR where CLDR has one and it is not outdated or truncated; otherwise the name given by the national source. The "
    "choice for each unit of version 0.3.0, with the reason for every departure from CLDR, is in "
    "national_adm1_units_v030.csv. In France, the name in the official geographic code of INSEE; elsewhere, as given by "
    "the source. For a contested area, its English name."
)


def fields_v030() -> list[tuple]:
    out = []
    for f in p20.FIELDS:
        name, typ, nullable, nullm, desc, unit = f
        if name == "name":
            desc = NAME_DESCRIPTION
        elif name in ("unit_type_local", "unit_type_en"):
            assert "For first-level units added in version 0.2.0," in desc
            desc = desc.replace("For first-level units added in version 0.2.0,",
                                "For first-level units added in versions 0.2.0 and 0.3.0,")
        out.append((name, typ, nullable, nullm, desc, unit))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# The 15 national sources (RES_texts r1 section 3.2-3.3, decisions D3 of ARCH7). publisher and product are the strings of
# boundaries\national_sources_v030.csv, because the build matches them with the records of the boundaries meta.json
# (exact publisher, substring `match` of the product).
# ---------------------------------------------------------------------------------------------------------------------
CC_BY_4 = ("CC-BY-4.0", "Creative Commons Attribution 4.0 International", "https://creativecommons.org/licenses/by/4.0/")
CC_BY_3_IGO = ("CC-BY-3.0-IGO", "Creative Commons Attribution 3.0 IGO", "https://creativecommons.org/licenses/by/3.0/igo/")
HDX_NOTE = ("OCHA's copy of the national boundaries on the Humanitarian Data Exchange, licensed CC BY 3.0 IGO; the copy "
            "has not been compared with the national publisher's file.")
TWN_ATTRIBUTION = (
    "Ministry of the Interior Land Surveying and Mapping Center 2026 Village boundaries (TWD97 longitude and latitude), "
    "version 1150817. The Open Data is made available to the public under the Open Government Data License, User can "
    "make use of it when complying to the condition and obligation of its terms. Open Government Data License: "
    "http://data.gov.tw/license")

# keys: id, role, publisher, product, url, edition, retrieved_at (explicit day, see notes), match, license (id, name, url,
# family), attribution, basis (type, text, checked_at, checked_by, evidence_url)
SOURCES = [
    dict(id="col_dane_mgn", publisher="Departamento Administrativo Nacional de Estadística (DANE)",
         product="Marco Geoestadístico Nacional (MGN) 2018, departamentos",
         url="https://geoportal.dane.gov.co/", edition="2018", retrieved="2026-11-10", match=["Geoestad"],
         lic=("LicenseRef-DANE-terms", "Terms of use of DANE", "https://geoportal.dane.gov.co/", "attribution"),
         attribution="Fuente: Departamento Administrativo Nacional de Estadística: www.dane.gov.co",
         basis=("license",
                "The terms of use of DANE authorize use, transformation and analysis of its data, provided the source is "
                "cited as above. DANE may change its terms without notice; the terms in force on 2026-11-15 apply to this "
                "release.", "2026-11-15", "agent:RES7", "https://geoportal.dane.gov.co/")),
    dict(id="est_maaamet_counties", publisher="Maa- ja Ruumiamet", product="Haldus- ja asustusjaotus: maakonnad",
         url="https://geoportaal.maaamet.ee/", edition="2026-11-04", retrieved="2026-11-09", match=["maakonnad"],
         lic=("LicenseRef-Maaamet-open-data", "Open data terms of Maa- ja Ruumiamet", "https://geoportaal.maaamet.ee/",
              "attribution"),
         attribution=("Maa- ja Ruumiamet (Estonian Land and Spatial Development Board), counties; data as of "
                      "2026-11-04"),
         basis=("publisher_statement",
                "The open data terms of Maa- ja Ruumiamet allow free use and require the source and the date of the data "
                "to be named.", "2026-11-15", "agent:RES7", "https://geoportaal.maaamet.ee/")),
    dict(id="hkg_had_districts", publisher="Home Affairs Department (HAD)",
         product="Administrative boundaries of Hong Kong: 18 districts",
         url="https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/hksar_18_district_boundary.gml",
         edition="2026-11-15", retrieved="2026-11-15", match=["Hong Kong"],
         lic=("LicenseRef-DATA-GOV-HK-terms", "Terms and Conditions of DATA.GOV.HK",
              "https://data.gov.hk/en/terms-and-conditions", "attribution"),
         attribution=("Home Affairs Department, Government of the Hong Kong Special Administrative Region; data from "
                      "DATA.GOV.HK"),
         basis=("license",
                "Used under the Terms and Conditions of DATA.GOV.HK, which allow distribution for commercial and "
                "non-commercial purposes; users of the data agree to indemnify the Government of the Hong Kong SAR "
                "against claims arising from their use, reproduction or distribution of the data.", "2026-11-15",
                "agent:RES7", "https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/"
                              "hksar_18_district_boundary.gml")),
    dict(id="idn_big_provinces", publisher="Badan Informasi Geospasial (BIG)",
         product="Batas wilayah administrasi, layer BATAS_WILAYAH (kabupaten/kota), dissolved by province",
         url="https://geoservices.big.go.id/rbi/rest/services/BATASWILAYAH/BATAS_WILAYAH/MapServer/12",
         edition="2024-09-05", retrieved="2026-11-15", match=["BATAS_WILAYAH"],
         lic=("LicenseRef-no-license-statute", "No license stated by the publisher; Indonesian Law No. 28 of 2014, "
              "Article 43(b)", "https://peraturan.bpk.go.id/Details/38690/uu-no-28-tahun-2014", "attribution"),
         attribution=("Badan Informasi Geospasial (BIG), regency and city boundaries at 1:50,000 (2024), merged into "
                      "provinces by the project"),
         basis=("statute",
                "BIG publishes these boundaries without license terms. We found no statement reserving rights in the saved "
                "ISO 19115-3 metadata of three BIG boundary layers (the item page of the layer could not be read, and the "
                "map service did not return its description). The units are included on the basis of Indonesia's Law No. "
                "28 of 2014 on Copyright, Article 43(b), under which publication, distribution, communication and copying "
                "of anything made by or on behalf of the government is not an infringement unless declared protected. "
                "Under Article 35(2) of the same law, commercial use of works made in government service may entitle their "
                "creator to royalties; commercial reusers should check Indonesian law. Coordinates are rounded to four "
                "decimal places, following BIG Regulation No. 1 of 2026.", "2026-11-17", "agent:RES7",
                "https://peraturan.bpk.go.id/Details/38690/uu-no-28-tahun-2014")),
    dict(id="irl_tailte_counties", publisher="Tailte Éireann",
         product="Counties - National Statutory Boundaries - Ungeneralised - 2024",
         url="https://data-osi.opendata.arcgis.com/", edition="2024", retrieved="2026-11-15",
         match=["National Statutory Boundaries"], lic=CC_BY_4 + ("attribution",),
         attribution="Tailte Éireann, Counties – National Statutory Boundaries – Ungeneralised 2024",
         basis=("license", "The dataset page of Tailte Éireann on its open data portal states CC BY 4.0.", "2026-11-15",
                "agent:RES7", "https://data-osi.opendata.arcgis.com/")),
    dict(id="kor_sgis_sido", publisher="Statistics Korea (SGIS, now the National Data Agency)",
         product="SGIS administrative boundaries 2025 Q2 (sido)", url="https://www.data.go.kr/data/15129688/fileData.do",
         edition="2025-06-30", retrieved="2026-11-10", match=["SGIS administrative boundaries"],
         lic=("LicenseRef-data-go-kr-no-restriction", "Public Data Portal (data.go.kr): no restriction on the scope of use",
              "https://www.data.go.kr/data/15129688/fileData.do", "attribution"),
         attribution="Statistics Korea, SGIS administrative boundaries, 2nd quarter of 2025",
         basis=("publisher_statement",
                "The data.go.kr record of the dataset states no restriction on the scope of use; no license is named.",
                "2026-11-15", "agent:RES7", "https://www.data.go.kr/data/15129688/fileData.do")),
    dict(id="lva_vzd_address_register", publisher="Valsts zemes dienests (VZD)",
         product="Valsts adrešu reģistra atvērtie dati (Novadi, Pilsētas)", url="https://data.gov.lv/",
         edition="2026-10-07", retrieved="2026-11-15", match=["Valsts adrešu reģistra"], lic=CC_BY_4 + ("attribution",),
         attribution="Valsts zemes dienests (State Land Service of Latvia), State Address Register open data",
         basis=("license", "The dataset page on the open data portal of Latvia states CC BY 4.0.", "2026-11-15",
                "agent:RES7", "https://data.gov.lv/")),
    dict(id="lux_act_cantons", publisher="Administration du cadastre et de la topographie (ACT)",
         product="Limites administratives du Grand-Duché de Luxembourg (cantons)", url="https://data.public.lu/",
         edition="2026-10-05", retrieved="2026-11-09", match=["Limites administratives"],
         lic=("CC0-1.0", "Creative Commons CC0 1.0 Universal", "https://creativecommons.org/publicdomain/zero/1.0/",
              "public_domain"),
         attribution="Administration du cadastre et de la topographie (Luxembourg), cantons",
         basis=("license", "The dataset page on data.public.lu states CC0 1.0.", "2026-11-15", "agent:RES7",
                "https://data.public.lu/")),
    dict(id="mex_inegi_via_hdx", publisher="Instituto Nacional de Estadística y Geografía (INEGI)",
         product="Marco Geoestadístico (via OCHA, HDX COD-AB: mex_admin1)",
         url="https://data.humdata.org/dataset/cod-ab-mex", edition="2021-06-18", retrieved="2026-11-11",
         match=["mex_admin1"], lic=CC_BY_3_IGO + ("attribution",),
         attribution="via OCHA (HDX, COD-AB); source: INEGI",
         basis=("license", HDX_NOTE, "2026-11-15", "agent:RES7", "https://data.humdata.org/dataset/cod-ab-mex")),
    dict(id="nzl_statsnz_2025", publisher="Stats NZ",
         product="Regional Council 2025 (clipped); Territorial Authority 2025 (clipped)",
         url="https://datafinder.stats.govt.nz/", edition="2025", retrieved="2026-11-15",
         match=["Regional Council 2025", "Territorial Authority 2025"], lic=CC_BY_4 + ("attribution",),
         attribution=("Stats NZ – Tatauranga Aotearoa, Regional Council 2025 and Territorial Authority 2025 (clipped)"),
         basis=("license", "The dataset pages of Stats NZ on Stats NZ Datafinder state CC BY 4.0.", "2026-11-15",
                "agent:RES7", "https://datafinder.stats.govt.nz/")),
    dict(id="per_ign_departments", publisher="Instituto Geográfico Nacional (IGN)", product="Límites departamentales",
         url="https://datosabiertos.gob.pe/", edition="2026-11-09", retrieved="2026-11-09", match=["departamentales"],
         lic=("ODC-By-1.0", "Open Data Commons Attribution License v1.0", "https://opendatacommons.org/licenses/by/1-0/",
              "attribution"),
         attribution="Instituto Geográfico Nacional (Peru), Límites Departamentales, via datosabiertos.gob.pe",
         basis=("license", "The dataset page on the open data portal of Peru states ODC-By 1.0.", "2026-11-15",
                "agent:RES7", "https://datosabiertos.gob.pe/")),
    dict(id="phl_psa_via_hdx", publisher="Philippine Statistics Authority (PSA) / NAMRIA",
         product="Philippine Standard Geographic Code, regions (via OCHA, HDX COD-AB: phl_admin2, provinces dissolved "
                 "by region)", url="https://data.humdata.org/dataset/cod-ab-phl", edition="2025-02-13",
         retrieved="2026-11-11", match=["phl_admin2"], lic=CC_BY_3_IGO + ("attribution",),
         attribution=("via OCHA (HDX, COD-AB), provinces; source: PSA, NAMRIA; regions assembled by the project under "
                      "Republic Act No. 12000 and Executive Order No. 91"),
         basis=("license", HDX_NOTE, "2026-11-15", "agent:RES7", "https://data.humdata.org/dataset/cod-ab-phl")),
    dict(id="twn_nlsc_counties", publisher="Ministry of the Interior Land Surveying and Mapping Center (內政部國土測繪中心)",
         product="Village boundaries (村里界圖), dissolved by county",
         url="https://whgis-nlsc.moi.gov.tw/Opendata/Files.aspx", edition="2026-08-17", retrieved="2026-11-15",
         match=["Village boundaries"],
         lic=("LicenseRef-OGDL-Taiwan-1.0", "Open Government Data License, version 1.0 (Taiwan)",
              "http://data.gov.tw/license", "attribution"),
         attribution=TWN_ATTRIBUTION,
         basis=("license",
                "The Open Government Data License 1.0 grants use under its terms; Article 3(2) requires the attribution in "
                "the form of the annex of the license, which is used as the attribution text.", "2026-11-15",
                "agent:RES7", "http://data.gov.tw/license")),
    dict(id="tha_dopa_via_hdx", publisher="Royal Thai Survey Department / Department of Provincial Administration (DOPA)",
         product="Subnational administrative boundaries (via OCHA, HDX COD-AB: tha_admin1)",
         url="https://data.humdata.org/dataset/cod-ab-tha", edition="2022-01-22", retrieved="2026-11-11",
         match=["tha_admin1"], lic=CC_BY_3_IGO + ("attribution",),
         attribution="via OCHA (HDX, COD-AB); source: Royal Thai Survey Department",
         basis=("license", HDX_NOTE, "2026-11-15", "agent:RES7", "https://data.humdata.org/dataset/cod-ab-tha")),
    dict(id="vnm_gso_via_hdx", publisher="General Statistics Office of Viet Nam (GSO)",
         product="Subnational administrative boundaries, 34 units (via OCHA, HDX COD-AB: vnm_admin1)",
         url="https://data.humdata.org/dataset/cod-ab-vnm", edition="2025-09-25", retrieved="2026-11-10",
         match=["vnm_admin1"], lic=CC_BY_3_IGO + ("attribution",),
         attribution="via OCHA (HDX, COD-AB); source: General Statistics Office of Viet Nam",
         basis=("license", HDX_NOTE, "2026-11-15", "agent:RES7", "https://data.humdata.org/dataset/cod-ab-vnm")),
]
assert len(SOURCES) == 15


def source_block(s: dict) -> str:
    lid, lname, lurl, family = s["lic"]
    btype, btext, bat, bby, bev = s["basis"]
    match = ", ".join(q(m) for m in s["match"])
    lines = [
        f"  - source_id: {s['id']}",
        "    role: geometry",
        f"    publisher: {q(s['publisher'])}",
        f"    product: {q(s['product'])}",
        f"    url: {q(s['url'])}",
        f"    edition: {q(s['edition'])}",
        f"    retrieved_at: {q(s['retrieved'])}",
        "    current_through: null",
        f"    bnd_match: [{match}]",
        "    license:",
        f"      id: {lid}",
        f"      name: {q(lname)}",
        f"      url: {q(lurl)}",
        f"      family: {family}",
        f"      attribution_text: {q(s['attribution'])}",
        "    rights_basis:",
        f"      type: {btype}",
        f"      text: {q(btext)}",
        f"      checked_at: {q(bat)}",
        f"      checked_by: {q(bby)}",
        f"      evidence_url: {q(bev)}",
        "    publication_mode: open_licence",
    ]
    return "\n".join(lines) + "\n"


def block_description() -> list[str]:
    return folded("description: >-", DESCRIPTION, 2)


def block_fields() -> list[str]:
    out = ["fields:"]
    for name, typ, nullable, nullm, desc, unit in fields_v030():
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


BLOCKS = {
    "description": block_description,
    "fields": block_fields,
    "coverage": block_coverage,
    "verification": block_verification,
}


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    if not YAML_PATH.exists():
        print(f"STOP: {YAML_PATH} not found; run from the repository root")
        return 2
    raw = YAML_PATH.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    trailing_newline = bool(lines) and lines[-1] == ""
    if trailing_newline:
        lines = lines[:-1]
    blocks = p20.split_blocks(lines)
    keys = [k for k, _ in blocks]
    for k in list(BLOCKS) + ["sources"]:
        if k not in keys:
            print(f"STOP: block {k}: is not in {YAML_PATH}")
            return 2
    changed: list[str] = []
    new_blocks: list[tuple[str | None, list[str]]] = []
    for key, body in blocks:
        if key in BLOCKS:
            content, tail = p20.trim(body)
            new = BLOCKS[key]()
            if content != new:
                changed.append(f"replaced block {key}")
            new_blocks.append((key, new + tail))
        elif key == "sources":
            content, tail = p20.trim(body)
            text = "\n".join(content)
            m = re.search(r'^(\s+attribution_text: )"Country boundaries[^\n]*"\s*$', text, flags=re.M)
            if not m:
                print("STOP: attribution_text of natural_earth not found")
                return 2
            want = f"{m.group(1)}{q(NE_ATTRIBUTION)}"
            if m.group(0).rstrip() != want:
                text = text.replace(m.group(0), want)
                changed.append("set attribution_text of natural_earth")
            for s in SOURCES:
                if f"source_id: {s['id']}\n" not in text + "\n":
                    text = text + "\n" + source_block(s).rstrip("\n")
                    changed.append(f"added source {s['id']}")
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
