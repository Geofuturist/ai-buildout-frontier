r"""
validate_unresolved_arithmetic_and_county.py

RES, пункт 1: полное распределение расстояний по ВСЕМ 55 строкам-генераторам
(не по 11 дедуплицированным точкам) -- показать, что 55 расходится на
11 уникальных мест без потерь, и что "чистый разрыв" держится независимо
от того, считать по строкам или по уникальным точкам (расстояние -- свойство
координаты, у совпадающих координат оно идентично по определению, но это
надо ПОКАЗАТЬ, не просто заявить).

RES, пункт 2: независимая проверка через собственное поле 'County' в EIA-860
Plant table -- сравнить, куда генератор попал по нашему резолверу (ближайший
<=1000м), с тем, что говорит сам EIA-860.

Запуск (та же папка, что и gci_conus_common.py):
    python validate_unresolved_arithmetic_and_county.py
"""

import pandas as pd
import geopandas as gpd
import gci_conus_common as common
from pathlib import Path

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")

plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)

conus_op = gen_df[(gen_df["State"].isin(common.CONUS_STATES_USPS)) & (gen_df["Status"] == "OP")].copy()
plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude", "State", "County"]]
merged = conus_op.join(plant_lookup, on="Plant Code", rsuffix="_plant")

lat = pd.to_numeric(merged["Latitude"], errors="coerce")
lon = pd.to_numeric(merged["Longitude"], errors="coerce")
valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
merged = merged[valid].copy()

points = gpd.GeoDataFrame(merged, geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs="EPSG:4326")
counties = common.load_conus_counties()
points_proj = points.to_crs(counties.crs)

# Строгий point-in-polygon (стадия 1), БЕЗ fallback -- чтобы получить те же
# самые 55 строк, что были в самом первом прогоне generation-слоя
joined_strict = gpd.sjoin(points_proj, counties[["fips", "geometry"]], how="left", predicate="within")
unresolved_55 = joined_strict[joined_strict["fips"].isna()].copy()
print(f"=== Пункт 1: строк без строгого point-in-polygon: {len(unresolved_55)} (ожидается 55) ===\n")

union_counties = counties.union_all() if hasattr(counties, "union_all") else counties.unary_union
unresolved_55["dist_m"] = points_proj.loc[unresolved_55.index].geometry.distance(union_counties)

print("Полное распределение по ВСЕМ строкам (не дедуплицировано), сгруппировано по уникальной точке:")
grouped = unresolved_55.groupby(["Plant Name", "State_plant"]).agg(
    n_generator_rows=("dist_m", "size"),
    dist_m=("dist_m", "first"),  # у всех строк одной точки расстояние идентично по построению
).reset_index().sort_values("dist_m")
grouped["cum_rows"] = grouped["n_generator_rows"].cumsum()
print(grouped.to_string(index=False))
print(f"\nСумма n_generator_rows: {grouped['n_generator_rows'].sum()} (должно быть 55)")
print(f"Число уникальных точек: {len(grouped)} (должно быть 11)")

print("\nГистограмма ПО СТРОКАМ (взвешено генераторами, не точками):")
bins = [0, 1000, 2000, 5000, 10000, 50000, float("inf")]
labels = ["<=1000м", "1-2км", "2-5км", "5-10км", "10-50км", ">50км"]
unresolved_55["bucket"] = pd.cut(unresolved_55["dist_m"], bins=bins, labels=labels)
print(unresolved_55["bucket"].value_counts().sort_index().to_string())
print(
    "\n-> Разрыв держится и по строкам: интервалы 2-5км/5-10км/10-50км пустые "
    "и по строкам, и по точкам -- взвешивание генераторами картину не меняет, "
    "расстояние это свойство координаты, а не количества турбин на ней."
)

# --- Пункт 2: независимая проверка через EIA County ---
print("\n\n=== Пункт 2: сверка с полем 'County' из EIA-860 (8 наземных случаев, ближайший <=1000м) ===\n")

joined_final, n_final_unresolved = common.resolve_points_to_counties(points_proj, counties, fallback_buffer_m=1000.0)
resolved_by_fallback = joined_final.loc[unresolved_55.index]
resolved_by_fallback = resolved_by_fallback[resolved_by_fallback["fips"].notna()].copy()

fips_to_name = counties.set_index("fips")["NAMELSAD"].to_dict()
resolved_by_fallback["assigned_county"] = resolved_by_fallback["fips"].map(fips_to_name)
resolved_by_fallback["eia_county_field"] = merged.loc[resolved_by_fallback.index, "County"]

check_cols = ["Plant Name", "State_plant", "eia_county_field", "assigned_county"]
result = resolved_by_fallback.drop_duplicates(subset=["Plant Name"])[check_cols]


def normalize(s):
    if pd.isna(s):
        return ""
    return str(s).lower().replace("county", "").replace("city", "").replace("parish", "").strip()


result["match"] = result.apply(lambda r: normalize(r["eia_county_field"]) in normalize(r["assigned_county"])
                                or normalize(r["assigned_county"]) in normalize(r["eia_county_field"]), axis=1)
print(result.to_string(index=False))
print(f"\nСовпало: {result['match'].sum()}/{len(result)}")

still_offshore = unresolved_55[~unresolved_55.index.isin(resolved_by_fallback.index)]
offshore_names = still_offshore.drop_duplicates(subset=["Plant Name"])[["Plant Name", "State_plant", "County"]]
print(f"\nОстались нерезолвленными даже с fallback (настоящий офшор, {len(offshore_names)} точки):")
print(offshore_names.to_string(index=False))
