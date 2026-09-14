r"""
check_unresolved_generators.py -- какие именно 55 генераторов не попали
ни в один округ CONUS. Быстрая проверка (2-3 сек), не для продакшена --
просто посмотреть глазами, что это офшор/погранично-неточные точки, а не
системная дыра в одном регионе.
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
plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude", "State"]]
merged = conus_op.join(plant_lookup, on="Plant Code", rsuffix="_plant")

lat = pd.to_numeric(merged["Latitude"], errors="coerce")
lon = pd.to_numeric(merged["Longitude"], errors="coerce")
valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
merged = merged[valid].copy()

points = gpd.GeoDataFrame(merged, geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs="EPSG:4326")
counties = common.load_conus_counties()
points = points.to_crs(counties.crs)

joined = gpd.sjoin(points, counties[["fips", "geometry"]], how="left", predicate="within")
unresolved = joined[joined["fips"].isna()]

print(f"Всего нерезолвленных: {len(unresolved)}\n")
print("Распределение по State_plant:")
print(unresolved["State_plant"].value_counts().to_string())
print("\nПолный список (Plant Name, State, lat, lon, Summer Capacity):")
cols = ["Plant Name", "State_plant", "Latitude", "Longitude", "Summer Capacity (MW)"]
print(unresolved[cols].to_string(index=False))
