#!/usr/bin/env python3
"""
build_boundaries.py -- assemble abf-boundaries-v0.1.0.

Run (from repo root, after fetch_boundary_sources.py has succeeded):
    python scripts\\boundaries\\build_boundaries.py --sources-dir "D:\\GISData\\Boundaries\\sources" --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.1.0" --pov usa

Builds, per SPEC_BND_boundaries_v0_1.md S4:
  - ADM0 for the whole world (S4.1): merge Natural Earth by iso3 = ISO_A3_EH, with
    boundaries/adm0_overrides.csv resolving the "-99" rows. Expects 242 units.
  - France ADM1/ADM2 (S4.3, ne_dissolve / ne_as_is).
  - Britain ADM1 (S4.4, ne_dissolve); no ADM2 in v0.1.
  - USA ADM1/ADM2 (S4.5, national_conformed): Census counties/states conformed to
    Canada/Mexico, gaps split into water/land/coast (amendment 2), ADM1 = dissolve
    of the conformed ADM2.
  - Norway ADM1/ADM2 (S4.5 + amendments 1/1a, S4.7): Kartverket Inndelingsbase
    conformed to Sweden/Finland/Russia; display geometry additionally clipped to the
    NE Norway polygon (source has no coastline of its own); analysis geometry keeps
    the water. Svalbard ADM1 taken as-is from NE. Jan Mayen/Bouvet get no ADM1.

Writes, under --out-dir (SPEC S6):
    display/adm0.parquet + .geojson.gz
    display/adm1.parquet + .geojson.gz
    display/adm2.parquet + .geojson.gz
    display/adm0_disputed_unassigned.* -- written by validate_boundaries.py --init-whitelist,
                                            not here (it needs the ADM0 hole set, which is
                                            computed from the *output* files per SPEC S5).
    analysis/USA_adm1_cb2023_500k.parquet, analysis/USA_adm2_cb2023_500k.parquet
    analysis/NOR_adm1_inndelingsbase_20260101.parquet, analysis/NOR_adm2_inndelingsbase_20260101.parquet
    meta.json, build_log.json, sources_manifest.json (copied from --sources-dir), unit_hashes.csv

Then run validate_boundaries.py (see boundaries/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnd_common as c  # noqa: E402

T0 = time.time()


def log(msg: str) -> None:
    c.log(msg, T0)


# --------------------------------------------------------------------------
# Source loading
# --------------------------------------------------------------------------

def resolve_source(sources_dir: Path, manifest: dict, key: str) -> Path:
    """Return the path to actually read for a given source key: the extracted
    directory for a zip, or the file itself for a plain GeoJSON."""
    entry = manifest.get(key)
    if entry is None:
        raise c.BuildError(f"Source {key!r} is not in sources_manifest.json -- run fetch_boundary_sources.py first.")
    if entry.get("extracted_to"):
        extracted = Path(entry["extracted_to"])
        shp = list(extracted.glob("*.shp"))
        if shp:
            return shp[0]
        gj = list(extracted.glob("*.geojson"))
        if gj:
            return gj[0]
        raise c.BuildError(f"Source {key!r}: extracted directory {extracted} has no .shp or .geojson.")
    return Path(entry["path"])


def load_sources(sources_dir: Path) -> dict:
    manifest_path = sources_dir / "sources_manifest.json"
    if not manifest_path.exists():
        raise c.BuildError(f"{manifest_path} not found -- run fetch_boundary_sources.py --sources-dir first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    log("loading Natural Earth ADM0 (_usa)...")
    ne_adm0 = gpd.read_file(resolve_source(sources_dir, manifest, "ne_adm0_usa"))
    log(f"  {len(ne_adm0)} features")

    log("loading Natural Earth ADM1...")
    ne_adm1 = gpd.read_file(resolve_source(sources_dir, manifest, "ne_adm1"))
    log(f"  {len(ne_adm1)} features")

    log("loading ne_10m_lakes...")
    ne_lakes = gpd.read_file(resolve_source(sources_dir, manifest, "ne_lakes"))
    log(f"  {len(ne_lakes)} features")

    log("loading Census state/county...")
    census_state = gpd.read_file(resolve_source(sources_dir, manifest, "census_state"))
    census_county = gpd.read_file(resolve_source(sources_dir, manifest, "census_county"))
    log(f"  {len(census_state)} states, {len(census_county)} counties")

    log("loading Kartverket fylker/kommuner...")
    fylke_raw = gpd.read_file(resolve_source(sources_dir, manifest, "kartverket_fylker"))
    fylke_raw = fylke_raw[fylke_raw["objtype"] == "Fylke"].reset_index(drop=True)
    kommune_raw = gpd.read_file(resolve_source(sources_dir, manifest, "kartverket_kommuner"))
    kommune_raw = kommune_raw[kommune_raw["objtype"] == "Kommune"].reset_index(drop=True)
    log(f"  {len(fylke_raw)} fylke, {len(kommune_raw)} kommuner (Grense rows dropped)")

    return dict(
        manifest=manifest, ne_adm0=ne_adm0, ne_adm1=ne_adm1, ne_lakes=ne_lakes,
        census_state=census_state, census_county=census_county,
        fylke_raw=fylke_raw, kommune_raw=kommune_raw,
    )


# --------------------------------------------------------------------------
# S4.1 -- ADM0
# --------------------------------------------------------------------------

def build_adm0(ne_adm0_raw: gpd.GeoDataFrame, overrides: dict, pov: str, logger: c.BuildLogger) -> gpd.GeoDataFrame:
    ne = c.to_wgs84(ne_adm0_raw)
    ne = c.clean_geodataframe(ne)

    tagged = []
    for _, row in ne.iterrows():
        iso3, status = c.compute_iso3(row["ISO_A3_EH"], row["ADM0_A3"], overrides)
        tagged.append(dict(iso3=iso3, adm0_status=status, ADM0_A3=row["ADM0_A3"],
                            NAME=row["NAME"], TYPE=row["TYPE"], geometry=row["geometry"]))
    tagged = gpd.GeoDataFrame(tagged, crs=c.CRS_WGS84)

    out_rows = []
    for iso3, group in tagged.groupby("iso3"):
        geom = c.union_clean(group.geometry.values)
        src_refs = sorted(group["ADM0_A3"].tolist())
        main = group[group["ADM0_A3"] == iso3]
        if len(main) == 1:
            name, ne_type = main["NAME"].iloc[0], main["TYPE"].iloc[0]
        elif len(group) == 1:
            name, ne_type = group["NAME"].iloc[0], group["TYPE"].iloc[0]
        else:
            g2 = group.sort_values("NAME")
            name, ne_type = g2["NAME"].iloc[0], g2["TYPE"].iloc[0]
            logger.add(step="adm0_name_ambiguous", iso3=iso3, candidates=group["NAME"].tolist())
        out_rows.append(dict(
            unit_id=iso3, iso3=iso3, level="ADM0", parent_id=None, name=name,
            unit_type_local="country", unit_type_en="country", method="ne_merge",
            source=f"Natural Earth {c.NE_VERSION} (adm0_pov={pov})", source_vintage=c.NE_VERSION,
            license="public domain", boundary_vintage=c.NE_VERSION, src_ref=";".join(src_refs),
            adm0_status=group["adm0_status"].iloc[0], ne_type=ne_type, published=True,
            geometry=geom,
        ))
    adm0 = gpd.GeoDataFrame(out_rows, crs=c.CRS_WGS84)
    if len(adm0) != c.ADM0_EXPECTED_UNITS:
        raise c.BuildError(
            f"ADM0 unit count = {len(adm0)}, expected {c.ADM0_EXPECTED_UNITS} (SPEC S4.1 p.4, S9: stop and ask)."
        )
    logger.add(step="build_adm0", n_units=len(adm0), pov=pov)
    log(f"ADM0: {len(adm0)} units")
    return adm0


def assert_nesting(children: gpd.GeoDataFrame, parent_geom, country_iso3: str, logger: c.BuildLogger) -> None:
    """SPEC S4.2 / S5.10 p.4: verify each ADM1 unit nests in its ADM0 parent by
    geometry (>=99.9% of area), not by trusting a source attribute. Applies to
    ne_dissolve/ne_as_is countries (France, Britain); national_conformed countries
    (USA, Norway) are explicitly exempt here (their own coastline can extend beyond
    the NE contour into the sea) -- checked instead via the conform-residual gap/
    encroachment measure (validation check 3)."""
    bad = []
    for _, row in children.iterrows():
        frac = c.nesting_fraction(row["geometry"], parent_geom)
        if frac < c.NESTING_MIN_FRACTION:
            bad.append((row["unit_id"], round(frac, 5)))
    if bad:
        raise c.BuildError(
            f"{country_iso3}: {len(bad)} ADM1 unit(s) do not nest >=99.9% in their ADM0 "
            f"parent by geometry (SPEC S4.2/S5.10 p.4): {bad}. Stop and ask."
        )
    logger.add(step="assert_nesting", country=country_iso3, n_checked=len(children), min_fraction=c.NESTING_MIN_FRACTION)


# --------------------------------------------------------------------------
# S4.3 -- France
# --------------------------------------------------------------------------

def build_france(ne_adm1_raw: gpd.GeoDataFrame, logger: c.BuildLogger) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    fra = ne_adm1_raw[ne_adm1_raw["adm0_a3"] == "FRA"].copy()
    fra = c.to_wgs84(fra)
    fra = c.clean_geodataframe(fra)
    if len(fra) != 101:
        raise c.BuildError(f"France: {len(fra)} raw NE ADM1 units with adm0_a3=='FRA', expected 101 (SPEC S4.3).")

    def dept_code(iso_3166_2: str) -> str:
        suffix = iso_3166_2.split("-", 1)[1] if "-" in str(iso_3166_2) else str(iso_3166_2)
        return c.FRANCE_OVERSEAS_DEPT.get(suffix, suffix)

    fra["dept_code"] = fra["iso_3166_2"].apply(dept_code)

    def insee_region(region_name: str) -> str:
        if region_name not in c.FRANCE_REGION_TO_INSEE:
            raise c.BuildError(
                f"France: NE `region` value {region_name!r} has no INSEE mapping in SPEC S4.3. Stop and ask."
            )
        return c.FRANCE_REGION_TO_INSEE[region_name]

    fra["region_insee"] = fra["region"].apply(insee_region)

    adm2 = gpd.GeoDataFrame([
        dict(
            unit_id=f"FRA-2-{row.dept_code}", iso3="FRA", level="ADM2",
            parent_id=f"FRA-1-{row.region_insee}", name=row.name,
            unit_type_local="département", unit_type_en="department", method="ne_as_is",
            source=f"Natural Earth {c.NE_VERSION}", source_vintage=c.NE_VERSION,
            license="public domain", boundary_vintage=c.NE_VERSION, src_ref=row.adm1_code,
            published=True, geometry=row.geometry,
        )
        for row in fra.itertuples()
    ], crs=c.CRS_WGS84)

    diss = c.dissolve_clean(fra[["region_insee", "geometry"]], by="region_insee")
    name_lookup = fra.groupby("region_insee")["region"].first().to_dict()

    adm1 = gpd.GeoDataFrame([
        dict(
            unit_id=f"FRA-1-{row.region_insee}", iso3="FRA", level="ADM1", parent_id="FRA",
            name=name_lookup[row.region_insee], unit_type_local="région", unit_type_en="region",
            method="ne_dissolve", source=f"Natural Earth {c.NE_VERSION}", source_vintage=c.NE_VERSION,
            license="public domain", boundary_vintage=c.NE_VERSION, src_ref=row.region_insee,
            published=True, geometry=row.geometry,
        )
        for row in diss.itertuples()
    ], crs=c.CRS_WGS84)
    if len(adm1) != 18:
        raise c.BuildError(f"France ADM1 = {len(adm1)} after dissolve, expected 18.")

    logger.add(step="build_france", n_adm2=len(adm2), n_adm1=len(adm1))
    log(f"France: ADM2={len(adm2)} ADM1={len(adm1)}")
    return adm2, adm1


# --------------------------------------------------------------------------
# S4.4 -- Britain
# --------------------------------------------------------------------------

def build_britain(ne_adm1_raw: gpd.GeoDataFrame, logger: c.BuildLogger) -> gpd.GeoDataFrame:
    gbr = ne_adm1_raw[ne_adm1_raw["adm0_a3"] == "GBR"].copy()
    gbr = c.to_wgs84(gbr)
    gbr = c.clean_geodataframe(gbr)
    if len(gbr) != 232:
        raise c.BuildError(f"Britain: {len(gbr)} raw NE ADM1 units with adm0_a3=='GBR', expected 232 (SPEC S4.4).")

    diss = c.dissolve_clean(gbr[["gu_a3", "geometry"]], by="gu_a3")
    rows = []
    for row in diss.itertuples():
        gu = row.gu_a3
        if gu not in c.GBR_NATION_NAMES:
            raise c.BuildError(f"Britain: unexpected gu_a3={gu!r}, not one of {list(c.GBR_NATION_NAMES)}.")
        rows.append(dict(
            unit_id=f"GBR-1-{gu}", iso3="GBR", level="ADM1", parent_id="GBR",
            name=c.GBR_NATION_NAMES[gu], unit_type_local="country", unit_type_en="constituent country",
            method="ne_dissolve", source=f"Natural Earth {c.NE_VERSION}", source_vintage=c.NE_VERSION,
            license="public domain", boundary_vintage=c.NE_VERSION, src_ref=gu,
            published=True, geometry=row.geometry,
        ))
    adm1 = gpd.GeoDataFrame(rows, crs=c.CRS_WGS84)
    if len(adm1) != 4:
        raise c.BuildError(f"Britain ADM1 = {len(adm1)} after dissolve, expected 4.")
    logger.add(step="build_britain", n_adm1=len(adm1))
    log(f"Britain: ADM1={len(adm1)} (no ADM2 in v0.1)")
    return adm1


# --------------------------------------------------------------------------
# S4.5 -- USA (national_conformed)
# --------------------------------------------------------------------------

def build_usa(
    census_state_raw: gpd.GeoDataFrame, census_county_raw: gpd.GeoDataFrame,
    adm0: gpd.GeoDataFrame, lakes_union, logger: c.BuildLogger,
):
    county = c.to_wgs84(census_county_raw)
    county = county[~county["STATEFP"].astype(str).isin(c.USA_TERRITORY_STATEFP)].reset_index(drop=True)
    county = c.clean_geodataframe(county)
    if len(county) != 3144:
        raise c.BuildError(f"USA counties after excluding territories = {len(county)}, expected 3144 (SPEC S4.5).")
    county["unit_id"] = "USA-2-" + county["GEOID"].astype(str)
    county["parent_id"] = "USA-1-" + county["STATEFP"].astype(str)

    state = c.to_wgs84(census_state_raw)
    state = state[~state["STATEFP"].astype(str).isin(c.USA_TERRITORY_STATEFP)].reset_index(drop=True)
    state = c.clean_geodataframe(state)
    if len(state) != 51:
        raise c.BuildError(f"USA states after excluding territories = {len(state)}, expected 51.")

    # --- analysis geometry: Census as-is, no conforming (SPEC S4.7) ---
    analysis_adm2 = gpd.GeoDataFrame({
        "unit_id": county["unit_id"], "iso3": "USA", "level": "ADM2",
        "parent_id": county["parent_id"], "geometry": county.geometry,
    }, crs=c.CRS_WGS84)
    analysis_adm1 = gpd.GeoDataFrame({
        "unit_id": "USA-1-" + state["STATEFP"].astype(str), "iso3": "USA", "level": "ADM1",
        "parent_id": "USA", "geometry": state.geometry,
    }, crs=c.CRS_WGS84)

    # --- display geometry: conform to Canada/Mexico (SPEC S4.5 steps 1-6) ---
    usa_poly = adm0.loc[adm0["unit_id"] == "USA", "geometry"].iloc[0]
    neighbours = c.union_clean(adm0.loc[adm0["unit_id"].isin(c.USA_NEIGHBOUR_ISO3), "geometry"])

    display_county_in = county[["unit_id", "parent_id", "NAME", "GEOID", "geometry"]].copy()
    conformed, gap_report = c.conform_national(
        display_county_in, usa_poly, neighbours, lakes_union,
        clip_water=False, logger=logger, unit_id_col="unit_id",
    )

    display_adm2 = gpd.GeoDataFrame([
        dict(
            unit_id=row.unit_id, iso3="USA", level="ADM2", parent_id=row.parent_id, name=row.NAME,
            unit_type_local="county", unit_type_en="county-equivalent", method="national_conformed",
            source="Census cb_2023_us_county_500k", source_vintage="2023", license="U.S. Government Work",
            boundary_vintage="2023", src_ref=row.GEOID, published=True, geometry=row.geometry,
        )
        for row in conformed.itertuples()
    ], crs=c.CRS_WGS84)

    # ADM1 := dissolve conformed ADM2 by parent (SPEC S4.5 step 6)
    diss = c.dissolve_clean(display_adm2[["parent_id", "geometry"]], by="parent_id")
    name_lookup = dict(zip("USA-1-" + state["STATEFP"].astype(str), state["NAME"]))
    display_adm1 = gpd.GeoDataFrame([
        dict(
            unit_id=row.parent_id, iso3="USA", level="ADM1", parent_id="USA",
            name=name_lookup.get(row.parent_id, row.parent_id), unit_type_local="state", unit_type_en="state",
            method="national_conformed", source="Census cb_2023_us_state_500k (via ADM2 dissolve)",
            source_vintage="2023", license="U.S. Government Work", boundary_vintage="2023",
            src_ref=row.parent_id.replace("USA-1-", ""), published=True, geometry=row.geometry,
        )
        for row in diss.itertuples()
    ], crs=c.CRS_WGS84)
    if len(display_adm1) != 51:
        raise c.BuildError(f"USA ADM1 after dissolve = {len(display_adm1)}, expected 51.")

    # cross-check dissolved ADM1 vs Census state file (report only, SPEC S4.5)
    state_geom_lookup = dict(zip("USA-1-" + state["STATEFP"].astype(str), state.geometry))
    symdiffs = []
    for row in display_adm1.itertuples():
        census_geom = state_geom_lookup.get(row.unit_id)
        if census_geom is None:
            continue
        sd = shapely.symmetric_difference(row.geometry, census_geom)
        symdiffs.append((row.unit_id, c.area_km2(sd)))
    symdiffs.sort(key=lambda t: -t[1])
    cross_check = {
        "max_symdiff_km2": round(symdiffs[0][1], 4) if symdiffs else None,
        "mean_symdiff_km2": round(sum(v for _, v in symdiffs) / len(symdiffs), 6) if symdiffs else None,
        "n_states_checked": len(symdiffs),
        "top10": [(uid, round(v, 4)) for uid, v in symdiffs[:10]],
        "note": "symdiff is expected to be > 0 here -- this compares the CONFORMED "
                "(encroachment removed, land gaps re-attached) ADM1 against the raw, "
                "unconformed Census state file, so it is largely measuring how much "
                "conforming moved along the Canada/Mexico border, concentrated in the "
                "states that actually touch it. See build_log.json step=remove_encroachment "
                "and step=assign_land_gap for the per-unit breakdown.",
    }

    logger.add(step="build_usa", n_adm2=len(display_adm2), n_adm1=len(display_adm1),
               gap_report=asdict(gap_report), cross_check_adm1_vs_census=cross_check)
    log(f"USA: ADM2={len(display_adm2)} ADM1={len(display_adm1)} "
        f"encroach_removed+gap_report_captured, max ADM1-vs-Census symdiff={cross_check['max_symdiff_km2']}km2")
    return display_adm2, display_adm1, analysis_adm2, analysis_adm1, gap_report, cross_check


# --------------------------------------------------------------------------
# S4.5 + amendments 1/1a -- Norway (national_conformed)
# --------------------------------------------------------------------------

def build_norway(
    fylke_raw: gpd.GeoDataFrame, kommune_raw: gpd.GeoDataFrame, ne_adm1_raw: gpd.GeoDataFrame,
    adm0: gpd.GeoDataFrame, lakes_union, logger: c.BuildLogger,
):
    fylke = c.to_wgs84(fylke_raw)  # source CRS EPSG:3135 -- to_wgs84 reprojects explicitly
    fylke = c.clean_geodataframe(fylke)
    if len(fylke) != 15:
        raise c.BuildError(f"Norway fylke = {len(fylke)}, expected 15 (SPEC S4.5).")
    fylke["fylkesnummer"] = fylke["fylkesnummer"].astype(str).str.zfill(2)

    kommune = c.to_wgs84(kommune_raw)  # source CRS EPSG:25833
    kommune = c.clean_geodataframe(kommune)
    if len(kommune) != 357:
        raise c.BuildError(f"Norway kommune = {len(kommune)}, expected 357 (SPEC S4.5).")
    kommune["kommunenummer"] = kommune["kommunenummer"].astype(str).str.zfill(4)
    kommune["parent_fylke"] = kommune["kommunenummer"].str[:2]
    kommune["unit_id"] = "NOR-2-" + kommune["kommunenummer"]
    kommune["parent_id"] = "NOR-1-" + kommune["parent_fylke"]

    # --- analysis geometry: Inndelingsbase as-is, water included (SPEC S4.7) ---
    analysis_adm2 = gpd.GeoDataFrame({
        "unit_id": kommune["unit_id"], "iso3": "NOR", "level": "ADM2",
        "parent_id": kommune["parent_id"], "geometry": kommune.geometry,
    }, crs=c.CRS_WGS84)
    analysis_adm1 = gpd.GeoDataFrame({
        "unit_id": "NOR-1-" + fylke["fylkesnummer"], "iso3": "NOR", "level": "ADM1",
        "parent_id": "NOR", "geometry": fylke.geometry,
    }, crs=c.CRS_WGS84)

    nor_poly = adm0.loc[adm0["unit_id"] == "NOR", "geometry"].iloc[0]
    neighbours = c.union_clean(adm0.loc[adm0["unit_id"].isin(c.NOR_NEIGHBOUR_ISO3), "geometry"])

    # Svalbard -- ADM1 taken as-is from raw NE ADM1 (SPEC S4.5); excluded from the gap
    # search below so it is not mistaken for a hole in Norway's ADM0 coverage.
    ne_adm1 = c.to_wgs84(ne_adm1_raw)
    svalbard = ne_adm1[ne_adm1["name"] == "Svalbard"]
    if len(svalbard) != 1:
        raise c.BuildError(f"Expected exactly 1 NE ADM1 row named 'Svalbard', found {len(svalbard)}.")
    svalbard_geom = c.clean(svalbard.geometry.iloc[0])

    # --- display geometry: conform to Sweden/Finland/Russia, then clip to NE Norway
    # polygon (amendment 1/1a -- Inndelingsbase has no coastline of its own) ---
    display_kommune_in = kommune[["unit_id", "parent_id", "kommunenavn", "kommunenummer", "geometry"]].copy()
    conformed, gap_report = c.conform_national(
        display_kommune_in, nor_poly, neighbours, lakes_union,
        clip_water=True, exclude_from_gaps=svalbard_geom,
        logger=logger, unit_id_col="unit_id",
    )

    display_adm2 = gpd.GeoDataFrame([
        dict(
            unit_id=row.unit_id, iso3="NOR", level="ADM2", parent_id=row.parent_id, name=row.kommunenavn,
            unit_type_local="kommune", unit_type_en="municipality", method="national_conformed",
            source="Kartverket, Administrative enheter kommuner (Inndelingsbase)", source_vintage="2026-01-01",
            license="CC BY 4.0", boundary_vintage="2026-01-01", src_ref=row.kommunenummer,
            published=True, geometry=row.geometry,
        )
        for row in conformed.itertuples()
    ], crs=c.CRS_WGS84)

    diss = c.dissolve_clean(display_adm2[["parent_id", "geometry"]], by="parent_id")
    name_lookup = dict(zip("NOR-1-" + fylke["fylkesnummer"], fylke["fylkesnavn"]))
    adm1_rows = [
        dict(
            unit_id=row.parent_id, iso3="NOR", level="ADM1", parent_id="NOR",
            name=name_lookup.get(row.parent_id, row.parent_id), unit_type_local="fylke", unit_type_en="county",
            method="national_conformed", source="Kartverket, Administrative enheter fylker (Inndelingsbase), via ADM2 dissolve",
            source_vintage="2026-01-01", license="CC BY 4.0", boundary_vintage="2026-01-01",
            src_ref=row.parent_id.replace("NOR-1-", ""), published=True, geometry=row.geometry,
        )
        for row in diss.itertuples()
    ]
    # Svalbard: ADM1 from NE as-is, unit_id NOR-1-21, no ADM2 (SPEC S4.5/S5.12)
    adm1_rows.append(dict(
        unit_id="NOR-1-21", iso3="NOR", level="ADM1", parent_id="NOR", name="Svalbard",
        unit_type_local="territory outside fylke", unit_type_en="territory outside fylke",
        method="ne_as_is", source=f"Natural Earth {c.NE_VERSION}", source_vintage=c.NE_VERSION,
        license="public domain", boundary_vintage=c.NE_VERSION, src_ref="NOR-901",
        published=True, geometry=svalbard_geom,
    ))
    display_adm1 = gpd.GeoDataFrame(adm1_rows, crs=c.CRS_WGS84)
    if len(display_adm1) != 16:
        raise c.BuildError(f"Norway ADM1 after dissolve + Svalbard = {len(display_adm1)}, expected 16.")

    # cross-check dissolved fylke (conformed+clipped) vs Kartverket fylke file (report only)
    fylke_geom_lookup = dict(zip("NOR-1-" + fylke["fylkesnummer"], fylke.geometry))
    symdiffs = []
    for row in display_adm1.itertuples():
        if row.unit_id == "NOR-1-21":
            continue
        kv_geom = fylke_geom_lookup.get(row.unit_id)
        if kv_geom is None:
            continue
        # compare against the *clipped* (display) version of the Kartverket fylke, since
        # the raw Kartverket fylke still carries open water that display geometry does not
        kv_geom_clipped = c.clean(shapely.intersection(kv_geom, nor_poly))
        sd = shapely.symmetric_difference(row.geometry, kv_geom_clipped)
        symdiffs.append((row.unit_id, c.area_km2(sd)))
    symdiffs.sort(key=lambda t: -t[1])
    cross_check = {
        "max_symdiff_km2": round(symdiffs[0][1], 4) if symdiffs else None,
        "mean_symdiff_km2": round(sum(v for _, v in symdiffs) / len(symdiffs), 6) if symdiffs else None,
        "n_fylke_checked": len(symdiffs),
        "top10": [(uid, round(v, 4)) for uid, v in symdiffs[:10]],
        "note": "symdiff compares the CONFORMED+clipped ADM1 against the raw Kartverket "
                "fylke file clipped to the NE Norway polygon (so open water is excluded "
                "from both sides fairly) -- a nonzero value here mostly reflects "
                "encroachment removed at the Sweden/Finland/Russia border, concentrated "
                "in the fylke that actually touch it.",
    }

    logger.add(step="build_norway", n_adm2=len(display_adm2), n_adm1=len(display_adm1),
               gap_report=asdict(gap_report), cross_check_adm1_vs_kartverket=cross_check)
    log(f"Norway: ADM2={len(display_adm2)} ADM1={len(display_adm1)} (incl. Svalbard), "
        f"max ADM1-vs-Kartverket(clipped) symdiff={cross_check['max_symdiff_km2']}km2")
    return display_adm2, display_adm1, analysis_adm2, analysis_adm1, gap_report, cross_check


# --------------------------------------------------------------------------
# meta.json / unit_hashes.csv
# --------------------------------------------------------------------------

def geom_hash(geom) -> str:
    return hashlib.sha256(shapely.to_wkb(geom, output_dimension=2)).hexdigest()[:16]


def write_unit_hashes(frames: list[gpd.GeoDataFrame], path: Path) -> None:
    rows = []
    for gdf in frames:
        for row in gdf.itertuples():
            rows.append({
                "unit_id": row.unit_id,
                "geom_sha256_16": geom_hash(row.geometry),
                "attr_sha256_16": hashlib.sha256(
                    json.dumps(
                        {k: v for k, v in row._asdict().items() if k not in ("Index", "geometry")},
                        sort_keys=True, default=str,
                    ).encode()
                ).hexdigest()[:16],
            })
    df = pd.DataFrame(rows).sort_values("unit_id")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def build_meta(
    release: str, pov: str, manifest: dict, unit_counts: dict, out_dir: Path,
) -> dict:
    sources = []
    for key, entry in manifest.items():
        sources.append({
            "publisher": entry["publisher"], "product": entry["product"],
            "url": entry["url"], "retrieved_at": entry["retrieved_at"],
            "sha256": entry["sha256"], "license": entry["license"],
        })
    return {
        "release": release,
        "built_at": c.now_iso(),
        "adm0_pov": pov,
        "sources": sources,
        "unit_counts": unit_counts,
        "boundary_source": "Natural Earth 1:10m framework, conformed to national sources for USA and Norway",
        "disclaimer": "границы не выражают позицию проекта",
        "license": "CC BY 4.0",
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--pov", default="usa")
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path,
                     help="repo-relative dir with boundary_registry.csv / adm0_overrides.csv (default: boundaries, run from repo root)")
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    (out_dir / "display").mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis").mkdir(parents=True, exist_ok=True)

    overrides_path = args.boundaries_dir / "adm0_overrides.csv"
    if not overrides_path.exists():
        raise c.BuildError(f"{overrides_path} not found (run from repo root, or pass --boundaries-dir).")
    overrides = c.load_adm0_overrides(overrides_path)
    registry_path = args.boundaries_dir / "boundary_registry.csv"
    registry = c.read_registry(registry_path) if registry_path.exists() else None

    logger = c.BuildLogger()
    src = load_sources(args.sources_dir)

    lakes_union = c.union_clean(c.to_wgs84(src["ne_lakes"]).geometry.values)
    log(f"lakes union built ({len(src['ne_lakes'])} lake polygons)")

    adm0 = build_adm0(src["ne_adm0"], overrides, args.pov, logger)

    fra_adm2, fra_adm1 = build_france(src["ne_adm1"], logger)
    assert_nesting(fra_adm1, adm0.loc[adm0["unit_id"] == "FRA", "geometry"].iloc[0], "FRA", logger)

    gbr_adm1 = build_britain(src["ne_adm1"], logger)
    assert_nesting(gbr_adm1, adm0.loc[adm0["unit_id"] == "GBR", "geometry"].iloc[0], "GBR", logger)

    usa_adm2, usa_adm1, usa_analysis_adm2, usa_analysis_adm1, usa_gap, usa_cross = build_usa(
        src["census_state"], src["census_county"], adm0, lakes_union, logger,
    )
    nor_adm2, nor_adm1, nor_analysis_adm2, nor_analysis_adm1, nor_gap, nor_cross = build_norway(
        src["fylke_raw"], src["kommune_raw"], src["ne_adm1"], adm0, lakes_union, logger,
    )

    # apply registry "verified" -> published, where a registry is available
    def apply_published(gdf: gpd.GeoDataFrame, iso3: str, level: str) -> gpd.GeoDataFrame:
        if registry is None:
            return gdf
        rows = registry[(registry["iso3"] == iso3) & (registry["level"] == level)]
        if len(rows):
            gdf = gdf.copy()
            gdf["published"] = rows["verified"].iloc[0].lower() == "true"
        return gdf

    fra_adm1 = apply_published(fra_adm1, "FRA", "ADM1")
    fra_adm2 = apply_published(fra_adm2, "FRA", "ADM2")
    gbr_adm1 = apply_published(gbr_adm1, "GBR", "ADM1")
    usa_adm1 = apply_published(usa_adm1, "USA", "ADM1")
    usa_adm2 = apply_published(usa_adm2, "USA", "ADM2")
    nor_adm1 = apply_published(nor_adm1, "NOR", "ADM1")
    nor_adm2 = apply_published(nor_adm2, "NOR", "ADM2")

    display_adm1 = pd.concat([fra_adm1, gbr_adm1, usa_adm1, nor_adm1], ignore_index=True)
    display_adm1 = gpd.GeoDataFrame(display_adm1, crs=c.CRS_WGS84)
    display_adm2 = pd.concat([fra_adm2, usa_adm2, nor_adm2], ignore_index=True)
    display_adm2 = gpd.GeoDataFrame(display_adm2, crs=c.CRS_WGS84)

    # --- validation check 1 sanity pre-pass (full check + report lives in validate_boundaries.py) ---
    for level_name, gdf in [("ADM0", adm0), ("ADM1", display_adm1), ("ADM2", display_adm2)]:
        overlaps = c.pairwise_overlaps(gdf)
        if overlaps:
            log(f"WARNING: {level_name} has {len(overlaps)} overlapping pairs > {c.OVERLAP_TOL_KM2}km2 "
                f"(full detail in validate_boundaries.py's report)")
        logger.add(step="overlap_prepass", level=level_name, n_overlaps=len(overlaps))

    # --- write display layers ---
    c.write_parquet(adm0, out_dir / "display" / "adm0.parquet")
    c.write_geojson_gz(adm0, out_dir / "display" / "adm0.geojson.gz")
    c.write_parquet(display_adm1, out_dir / "display" / "adm1.parquet")
    c.write_geojson_gz(display_adm1, out_dir / "display" / "adm1.geojson.gz")
    c.write_parquet(display_adm2, out_dir / "display" / "adm2.parquet")
    c.write_geojson_gz(display_adm2, out_dir / "display" / "adm2.geojson.gz")
    log("display/adm0, adm1, adm2 written (adm0_disputed_unassigned is written by validate_boundaries.py --init-whitelist)")

    # --- write analysis layers (USA, Norway only -- SPEC S4.7) ---
    c.write_parquet(usa_analysis_adm1, out_dir / "analysis" / "USA_adm1_cb2023_500k.parquet")
    c.write_parquet(usa_analysis_adm2, out_dir / "analysis" / "USA_adm2_cb2023_500k.parquet")
    c.write_parquet(nor_analysis_adm1, out_dir / "analysis" / "NOR_adm1_inndelingsbase_20260101.parquet")
    c.write_parquet(nor_analysis_adm2, out_dir / "analysis" / "NOR_adm2_inndelingsbase_20260101.parquet")
    log("analysis/USA_*, NOR_* written")

    # --- unit_hashes.csv (reproducibility check, SPEC S8) ---
    write_unit_hashes([adm0, display_adm1, display_adm2], out_dir / "unit_hashes.csv")

    # --- sources_manifest.json (copied from --sources-dir into --out-dir, SPEC S6) ---
    shutil.copy(args.sources_dir / "sources_manifest.json", out_dir / "sources_manifest.json")

    # --- meta.json ---
    unit_counts = {
        "ADM0": len(adm0),
        "ADM1": {"total": len(display_adm1), "USA": len(usa_adm1), "FRA": len(fra_adm1),
                  "GBR": len(gbr_adm1), "NOR": len(nor_adm1)},
        "ADM2": {"total": len(display_adm2), "USA": len(usa_adm2), "FRA": len(fra_adm2), "NOR": len(nor_adm2)},
    }
    meta = build_meta("abf-boundaries-v0.1.0", args.pov, src["manifest"], unit_counts, out_dir)
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log("meta.json written")

    # --- build_log.json ---
    logger.write(out_dir / "build_log.json")
    log(f"build_log.json written ({len(logger.entries)} entries)")

    # --- console summary for the handoff report ---
    print("\n=== BUILD SUMMARY ===")
    print(f"ADM0: {len(adm0)} units (expected {c.ADM0_EXPECTED_UNITS})")
    print(f"ADM1: {len(display_adm1)} (USA {len(usa_adm1)}, FRA {len(fra_adm1)}, GBR {len(gbr_adm1)}, NOR {len(nor_adm1)})")
    print(f"ADM2: {len(display_adm2)} (USA {len(usa_adm2)}, FRA {len(fra_adm2)}, NOR {len(nor_adm2)})")
    print(f"USA gap report: {usa_gap}")
    print(f"USA ADM1 vs Census cross-check: {usa_cross}")
    print(f"Norway gap report: {nor_gap}")
    print(f"Norway ADM1 vs Kartverket cross-check: {nor_cross}")
    print(f"\nTotal build time: {time.time() - T0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
