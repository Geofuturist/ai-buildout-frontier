r"""
diag_generation_full.py -- полная версия слоя generation с print(flush=True)
на каждом шаге. Если отработает до конца -- это и есть готовый результат,
отдельно build_layer_generation_eia860.py запускать уже не нужно.
"""
print("1. Старт", flush=True)

from pathlib import Path
import datetime as dt
import pandas as pd
import geopandas as gpd
import gci_conus_common as common

print("2. Импорты done", flush=True)

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")

plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)
print(f"3. EIA-860 прочитан: plant={len(plant_df)}, gen={len(gen_df)}", flush=True)

conus_op = gen_df[(gen_df["State"].isin(common.CONUS_STATES_USPS)) & (gen_df["Status"] == "OP")].copy()
print(f"4. CONUS+OP отфильтровано: {len(conus_op)}", flush=True)

plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude"]]
merged = conus_op.join(plant_lookup, on="Plant Code", rsuffix="_plant")
print(f"5. Join с координатами: {len(merged)}", flush=True)

lat = pd.to_numeric(merged["Latitude"], errors="coerce")
lon = pd.to_numeric(merged["Longitude"], errors="coerce")
valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
merged = merged[valid].copy()
print(f"6. Валидных координат: {len(merged)}", flush=True)

points = gpd.GeoDataFrame(merged, geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs="EPSG:4326")
print(f"7. GeoDataFrame точек построен: {len(points)}", flush=True)

counties = common.load_conus_counties()
print(f"8. Границы округов загружены: {len(counties)}", flush=True)

points = points.to_crs(counties.crs)
print("9. Точки репроецированы в CRS округов", flush=True)

print("10. Начинаю sjoin (точки в полигоны)...", flush=True)
joined = gpd.sjoin(points, counties[["fips", "geometry"]], how="left", predicate="within")
print(f"11. sjoin готов: {len(joined)} строк", flush=True)

n_unresolved = int(joined["fips"].isna().sum())
print(f"12. Не попали ни в один округ: {n_unresolved}", flush=True)
joined = joined[joined["fips"].notna()].copy()

joined["net_summer_capacity_mw"] = pd.to_numeric(joined["Summer Capacity (MW)"], errors="coerce")

agg = joined.groupby("fips").agg(
    net_summer_gen_mw=("net_summer_capacity_mw", "sum"),
    n_op_generators=("Generator ID", "count"),
    n_op_plants=("Plant Code", "nunique"),
).reset_index()
print(f"13. Агрегация по округам готова: {len(agg)} строк", flush=True)

result = counties.merge(agg, on="fips", how="left")
result["net_summer_gen_mw"] = result["net_summer_gen_mw"].fillna(0.0)
result["n_op_generators"] = result["n_op_generators"].fillna(0).astype(int)
result["n_op_plants"] = result["n_op_plants"].fillna(0).astype(int)
print(f"14. Merge с полным списком округов готов: {len(result)} строк", flush=True)

snapshot_date = dt.date.today().strftime("%Y%m%d")
meta = {
    "source": "EIA Form 860, Schedule 3 (Generator, Operable/OP) + Schedule 2 (Plant)",
    "source_url": "https://www.eia.gov/electricity/data/eia860/",
    "vintage": "data year 2024, final release 2025-09-09",
    "license": "US government work — public domain (17 U.S.C. § 105)",
    "coverage": "48 states + DC (CONUS)",
    "n_units_covered": int(len(joined)),
    "n_units_no_data": n_unresolved,
    "known_gaps": (
        f"{n_unresolved} генераторов с валидными координатами не резолвятся ни в один округ CONUS "
        "(offshore-объекты вроде CVOW, либо координаты на самой границе штата/страны) — исключены "
        "из агрегации. Статусы OA/OS/SB исключены сознательно — слой отражает текущую действующую "
        "генерацию, не номинальную мощность парка."
    ),
}

print("15. Начинаю запись файлов (CSV + GeoJSON + meta.json)...", flush=True)
common.write_layer_outputs(
    "generation_eia860",
    result[["fips", "NAME", "NAMELSAD", "net_summer_gen_mw", "n_op_generators", "n_op_plants", "geometry"]],
    meta,
    snapshot_date,
)
print("16. ГОТОВО. Файлы записаны в data\\conus\\", flush=True)
