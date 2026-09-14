r"""
build_layer_generation_eia860.py
===================================
ТЗ-1, слой 1/5: net_summer_gen_mw по округу, CONUS.
EIA Form 860, Schedule 3 Generator (Operable, Status=='OP') + Plant (координаты).

Pre-flight подтвердил: 23957 CONUS+OP генераторов, 100% с валидными
координатами. Статусы OA/OS (temporarily out of service) и SB (standby)
исключены той же логикой, что и в M2a.

Point-in-polygon с двухступенчатым разрешением (см. resolve_points_to_counties
в gci_conus_common.py): строгий within, затем ближайший округ <=1000м для
пограничных случаев. Найдено эмпирически на первом реальном прогоне: 8
станций (Gowanus NY ~500+МВт, Port Washington WI ~1.2ГВт и другие) реально
наземные, но их EIA-координата лежит в считанных метрах от береговой линии
cb-границ (500k обрезан по берегу) -- без этого шага молча теряли бы больше
1.7 ГВт для Kings County NY и Milwaukee County WI. Настоящий офшор (Block
Island, South Fork Wind, CVOW) остаётся корректно исключён -- расстояния
до берега там 5-43 км, порог 1000м их не задевает.

Запуск (та же папка, что и gci_conus_common.py):
    python build_layer_generation_eia860.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from gci_conus_common import (
    CONUS_STATES_USPS,
    load_conus_counties,
    resolve_points_to_counties,
    write_layer_outputs,
    log,
)

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")

LAYER_NAME = "generation_eia860"
SOURCE_URL = "https://www.eia.gov/electricity/data/eia860/"
VINTAGE = "data year 2024, final release 2025-09-09"
BOUNDARY_FALLBACK_M = 1000.0


def main() -> None:
    import pandas as pd
    import geopandas as gpd

    if not PLANT_XLSX.exists() or not GENERATOR_XLSX.exists():
        log.error("Не найден один из файлов EIA-860.")
        return

    log.info("Читаю EIA-860...")
    plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
    gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)

    conus_op = gen_df[(gen_df["State"].isin(CONUS_STATES_USPS)) & (gen_df["Status"] == "OP")].copy()
    log.info("CONUS + Status=='OP': %d генераторов", len(conus_op))

    plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude"]]
    merged = conus_op.join(plant_lookup, on="Plant Code", rsuffix="_plant")

    lat = pd.to_numeric(merged["Latitude"], errors="coerce")
    lon = pd.to_numeric(merged["Longitude"], errors="coerce")
    valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
    merged = merged[valid].copy()
    log.info("С валидными координатами: %d", len(merged))

    points = gpd.GeoDataFrame(
        merged,
        geometry=gpd.points_from_xy(lon[valid], lat[valid]),
        crs="EPSG:4326",
    )

    counties = load_conus_counties()
    points = points.to_crs(counties.crs)

    log.info("Point-in-polygon (строгий + ближайший <=%.0fм для граничных случаев)...", BOUNDARY_FALLBACK_M)
    joined, n_unresolved = resolve_points_to_counties(points, counties, fallback_buffer_m=BOUNDARY_FALLBACK_M)

    if n_unresolved:
        unresolved_names = joined.loc[joined["fips"].isna(), "Plant Name"].dropna().unique().tolist()
        log.warning(
            "%d генераторов не резолвлены даже с запасом %.0fм (вероятно настоящий офшор) — "
            "исключены из агрегации. Примеры: %s",
            n_unresolved, BOUNDARY_FALLBACK_M, unresolved_names[:10],
        )
    joined = joined[joined["fips"].notna()].copy()

    joined["net_summer_capacity_mw"] = pd.to_numeric(joined["Summer Capacity (MW)"], errors="coerce")

    agg = joined.groupby("fips").agg(
        net_summer_gen_mw=("net_summer_capacity_mw", "sum"),
        n_op_generators=("Generator ID", "count"),
        n_op_plants=("Plant Code", "nunique"),
    ).reset_index()

    result = counties.merge(agg, on="fips", how="left")
    result["net_summer_gen_mw"] = result["net_summer_gen_mw"].fillna(0.0)
    result["n_op_generators"] = result["n_op_generators"].fillna(0).astype(int)
    result["n_op_plants"] = result["n_op_plants"].fillna(0).astype(int)

    n_zero = (result["n_op_generators"] == 0).sum()
    log.info("Округов с нулевой генерацией: %d/%d", n_zero, len(result))

    snapshot_date = dt.date.today().strftime("%Y%m%d")
    meta = {
        "source": "EIA Form 860, Schedule 3 (Generator, Operable/OP) + Schedule 2 (Plant)",
        "source_url": SOURCE_URL,
        "vintage": VINTAGE,
        "license": "US government work — public domain (17 U.S.C. § 105)",
        "coverage": "48 states + DC (CONUS)",
        "n_units_covered": int(len(joined)),
        "n_units_no_data": int(n_unresolved),
        "known_gaps": (
            f"{n_unresolved} генераторов с валидными координатами не резолвятся ни в один округ CONUS "
            f"даже с запасом {BOUNDARY_FALLBACK_M:.0f}м (настоящий офшор — Block Island Wind Farm, "
            "South Fork Wind, Coastal Virginia Offshore Wind; расстояние до берега 5-43 км) — исключены "
            "из агрегации. Статусы OA/OS (временно не в работе) и SB (standby) исключены сознательно — "
            "слой отражает текущую действующую генерацию, не номинальную мощность парка. Point-in-polygon "
            f"использует запас {BOUNDARY_FALLBACK_M:.0f}м для точек у самой границы округа (обрезка "
            "береговой линии в cb-границах 500k, международная речная граница) — откалибровано "
            "эмпирически на реальном разрыве между береговыми случаями (6-718м) и офшором (4865-42758м)."
        ),
    }

    write_layer_outputs(
        LAYER_NAME,
        result[["fips", "NAME", "NAMELSAD", "net_summer_gen_mw", "n_op_generators", "n_op_plants", "geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
