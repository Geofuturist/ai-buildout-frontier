r"""
check_unresolved_distances.py -- для каждой из 55 нерезолвленных точек:
расстояние до ближайшего полигона округа (в метрах, JOIN_CRS уже метровый).
Нужно, чтобы выбрать буфер осознанно, а не на глаз -- пограничные-береговые
случаи должны быть в районе десятков-сотен метров, настоящий офшор -- в
районе километров/десятков км.
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
points = points.to_crs(counties.crs)  # метровый CRS (EPSG:5070)

joined = gpd.sjoin(points, counties[["fips", "geometry"]], how="left", predicate="within")
unresolved = points.loc[joined[joined["fips"].isna()].index].copy()

# Дедуплицируем по (Plant Name, geometry) -- один расчёт на физическую точку, не на каждый генератор
unique_pts = unresolved.drop_duplicates(subset=["Plant Name", "geometry"])[["Plant Name", "State_plant", "geometry"]]

union_counties = counties.union_all() if hasattr(counties, "union_all") else counties.unary_union

print(f"{'Plant Name':<45} {'State':<6} {'Дистанция до ближайшего округа, м':>35}")
for _, row in unique_pts.sort_values("Plant Name").iterrows():
    dist_m = row.geometry.distance(union_counties)
    print(f"{row['Plant Name']:<45} {row['State_plant']:<6} {dist_m:>35,.0f}")
